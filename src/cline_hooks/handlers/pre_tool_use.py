from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import bashlex
import bashlex.errors
import git

from cline_hooks.core.outcome import Disposition, Outcome
from cline_hooks.core.parameters import (
    AttemptCompletionParameters,
    FileEditParameters,
    McpToolUse,
    PlanModeRespondParameters,
    ReadParameters,
    ShellParameters,
)
from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.registry import TOOL_HANDLERS, hook_handler, tool_handler
from cline_hooks.core.vocabulary import (
    CanonicalHook,
    CanonicalTool,
    FILE_EDIT_TOOLS,
    KNOWN_TOOLS,
    PluginScope,
    SHELL_TOOLS,
)
from cline_hooks.handlers.commands import (
    check_rules,
    contains_comment,
    extract_commands,
    extract_replacement_blocks,
    get_all_command_rules,
    is_git_push,
)
from cline_hooks.handlers.push_guard import marker_above_repo
from cline_hooks.state.skills import (
    is_skill_called as _is_skill_called,
    required_skill_for,
)
from cline_hooks.state.store import TaskStateStore

try:
    from llm_prompts.install import (
        get_managed_files as _get_managed_files_impl,
        get_source_for_managed_file as _get_source_impl,
    )
except ImportError:
    _get_managed_files_impl = None
    _get_source_impl = None

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputPreToolUse, PreToolUseFields
    from cline_hooks.core.plugin import HooksPlugin

logger = logging.getLogger("hooks")

_LARGE_FILE_THRESHOLD = 1000
_EMOJI_THRESHOLD = 0x7F
_managed_files: set[str] | None = None


def _get_managed_files() -> set[str]:
    """Return cached set of managed file paths from the manifest."""
    global _managed_files  # noqa: PLW0603
    if _managed_files is None:
        if _get_managed_files_impl is not None:
            _managed_files = _get_managed_files_impl()
        else:
            _managed_files = set()
    return _managed_files


def _is_managed_path(path: str) -> bool:
    """Check if a file path is tracked in the llm-prompts manifest.

    Args:
        path: The file path to check.

    Returns:
        True if the file is managed by llm-prompts.
    """
    try:
        resolved = str(Path(path).resolve())
    except (OSError, ValueError):
        return False
    managed = _get_managed_files()
    if resolved in managed:
        return True
    return any(resolved.startswith(managed_path + "/") for managed_path in managed)


def _managed_source_instruction(path: str) -> str:
    """Return the edit instruction for a managed path, naming its source file.

    Args:
        path: The managed destination path.

    Returns:
        Instruction naming the resolved source file, or a generic instruction
        where the source cannot be resolved.
    """
    if _get_source_impl is not None:
        source = None
        with contextlib.suppress(Exception):
            source = _get_source_impl(path)
        if source:
            return f"MUST edit the source file {source} instead"
    return "MUST edit the source file instead"


def _starts_with_emoji(text: str) -> bool:
    """Check if text starts with a non-ASCII character (emoji canary).

    Args:
        text: The text to check.

    Returns:
        True if the first non-whitespace character is non-ASCII.
    """
    stripped = text.lstrip()
    return bool(stripped) and ord(stripped[0]) > _EMOJI_THRESHOLD


def _hook_result_outcome(
    hook_name: str,
    plugins: list[HooksPlugin],
    task_id: str,
    tool_name: str,
    **kwargs: object,
) -> Outcome:
    """Collect plugin results as an Outcome.

    Args:
        hook_name: The hook or plugin-scope name.
        plugins: Loaded plugin instances.
        task_id: The task identifier.
        tool_name: The tool being validated.
        **kwargs: Additional kwargs passed to on_hook.

    Returns:
        A BLOCK Outcome for a plugin block, an ALLOW Outcome carrying plugin
        notes, otherwise an empty Outcome.
    """
    result = collect_hook_results(
        plugins, hook_name, task_id=task_id, tool_name=tool_name, **kwargs
    )
    if result.block:
        return Outcome.block(result.block)
    if result.notes:
        return Outcome.allow("\n\n".join(result.notes), label="REMINDER")
    return Outcome()


@tool_handler(CanonicalHook.PRE_TOOL_USE, CanonicalTool.PLAN_MODE_RESPOND)
def _pre_plan_mode_respond(
    hook: HookInputPreToolUse, fields: PreToolUseFields, _plugins: list[HooksPlugin]
) -> Outcome:
    """Block a plan-mode response that doesn't start with the emoji canary.

    Args:
        hook: The hook input data.
        fields: The PreToolUse fields.
        _plugins: Loaded plugin instances (unused).

    Returns:
        A BLOCK Outcome if the response is missing the emoji canary.
    """
    response: str = PlanModeRespondParameters.build(fields.parameters).response
    if not _starts_with_emoji(response):
        return Outcome.block(
            "Response does not start with an emoji - context window may be degraded. "
            "MUST use the new_task tool to start a fresh context."
        )
    return Outcome()


@tool_handler(CanonicalHook.PRE_TOOL_USE, CanonicalTool.READ)
def _pre_read(
    hook: HookInputPreToolUse, fields: PreToolUseFields, _plugins: list[HooksPlugin]
) -> Outcome:
    """Block reading a file that's too large to read in full.

    Args:
        hook: The hook input data.
        fields: The PreToolUse fields.
        _plugins: Loaded plugin instances (unused).

    Returns:
        A BLOCK Outcome if the file exceeds the large-file threshold.
    """
    path: str = ReadParameters.build(fields.parameters).path
    if not path:
        return Outcome()
    try:
        line_count = (
            Path(path).read_text(encoding="utf-8", errors="replace").count("\n")
        )
    except OSError:
        return Outcome()
    if line_count > _LARGE_FILE_THRESHOLD:
        return Outcome.block(
            f"{path} is {line_count} lines. "
            "MUST use a tool such as search_files with specific patterns "
            "instead of reading the whole file."
        )
    return Outcome()


@tool_handler(CanonicalHook.PRE_TOOL_USE, *SHELL_TOOLS)
def _pre_shell(
    hook: HookInputPreToolUse, fields: PreToolUseFields, plugins: list[HooksPlugin]
) -> Outcome:
    """Enforce command rules, required skills, and the git-push guard.

    Args:
        hook: The hook input data.
        fields: The PreToolUse fields.
        plugins: Loaded plugin instances.

    Returns:
        A BLOCK Outcome for the first violated check, otherwise an empty Outcome.
    """
    command: str = ShellParameters.build(fields.parameters).command
    if not command:
        return Outcome()

    try:
        parsed = bashlex.parse(command)
    except bashlex.errors.ParsingError:
        logger.debug("Failed to parse command (unsupported shell syntax): %s", command)
        return Outcome()

    commands = extract_commands(parsed)

    violated_rule = check_rules(commands, get_all_command_rules(plugins))
    if violated_rule:
        return Outcome.block(violated_rule.message)

    required_skill = required_skill_for([cmd.name for cmd in commands])
    if required_skill and not _is_skill_called(hook.taskId, required_skill):
        return Outcome.block(
            f"MUST use the `{required_skill}` skill before running this command"
        )

    if is_git_push(commands):
        marker = marker_above_repo(hook.workspaceRoots)
        if marker:
            return Outcome.block(
                f"git push is blocked here: this repository is inside a managed "
                f"workspace (a '{marker}' entry was found at or above the repo root). "
                f"MUST use the workspace's own review/submit workflow instead of "
                f"pushing directly."
            )

    return Outcome()


@tool_handler(CanonicalHook.PRE_TOOL_USE, *FILE_EDIT_TOOLS)
def _pre_file_edit(
    hook: HookInputPreToolUse, fields: PreToolUseFields, _plugins: list[HooksPlugin]
) -> Outcome:
    """Block edits to managed files and flag disallowed comments in the diff.

    Args:
        hook: The hook input data.
        fields: The PreToolUse fields.
        _plugins: Loaded plugin instances (unused).

    Returns:
        A BLOCK Outcome for a managed-file edit, an ALLOW Outcome carrying
        comment/type-ignore notes, otherwise an empty Outcome.
    """
    params = FileEditParameters.build(fields.parameters)
    file_path = params.path
    if file_path and _is_managed_path(file_path):
        return Outcome.block(
            f"{file_path} is managed by llm-prompts. "
            f"{_managed_source_instruction(file_path)}, "
            "then run `llm-prompts update`."
        )

    diff = params.diff
    if not diff:
        return Outcome()

    replacement_blocks = extract_replacement_blocks(diff)
    logger.debug("block count: %s", len(replacement_blocks))

    notes: set[str] = set()

    for replacement_block in replacement_blocks:
        for line in replacement_block.split("\n"):
            if (stripped_line := line.strip()) and contains_comment(line):
                logger.debug("comment in line: %s", stripped_line)
                if "# type: ignore" in stripped_line and "ignore[" not in stripped_line:
                    notes.add(
                        "SHOULD NOT use type ignore comments; where necessary, MUST use a specific ignore."
                    )
                else:
                    notes.add(
                        "MUST NOT write comments explaining the reasoning for a specific change. "
                        "Comments SHOULD only be used to explain complex code. If comments are "
                        "required, consider a different approach."
                    )

    return Outcome.allow(*notes, label="REMINDER") if notes else Outcome()


@tool_handler(CanonicalHook.PRE_TOOL_USE, CanonicalTool.MCP)
def _pre_mcp(
    hook: HookInputPreToolUse, fields: PreToolUseFields, plugins: list[HooksPlugin]
) -> Outcome:
    """Dispatch a use_mcp_tool call to plugins' PreMcpToolUse handling.

    Args:
        hook: The hook input data.
        fields: The PreToolUse fields.
        plugins: Loaded plugin instances.

    Returns:
        The plugin-derived Outcome for this MCP tool call.
    """
    tool = McpToolUse.build(fields.parameters)
    return _hook_result_outcome(
        PluginScope.PRE_MCP_TOOL_USE,
        plugins,
        hook.taskId,
        fields.toolName,
        mcp_tool_name=tool.tool_name,
        mcp_arguments=tool.arguments,
        agent_type=hook.agentType,
    )


@tool_handler(CanonicalHook.PRE_TOOL_USE, CanonicalTool.ATTEMPT_COMPLETION)
def _pre_attempt_completion(
    hook: HookInputPreToolUse, fields: PreToolUseFields, plugins: list[HooksPlugin]
) -> Outcome:
    """Block finishing with incomplete task_progress items or a dirty working tree.

    Args:
        hook: The hook input data.
        fields: The PreToolUse fields.
        plugins: Loaded plugin instances.

    Returns:
        A BLOCK Outcome for incomplete task_progress or a dirty repo, merged
        with any plugin-supplied notes.
    """
    task_progress: str = (
        AttemptCompletionParameters.build(fields.parameters).task_progress or ""
    )
    incomplete = [
        line for line in task_progress.splitlines() if line.strip().startswith("- [ ]")
    ]
    if incomplete:
        return Outcome.block(
            f"task_progress has {len(incomplete)} incomplete item(s). MUST complete them before finishing."
        )

    outcome = Outcome()
    result = collect_hook_results(
        plugins, PluginScope.ATTEMPT_COMPLETION, task_id=hook.taskId
    )
    if result.notes:
        outcome = outcome.merge(
            Outcome.allow("\n\n".join(result.notes), label="IMPORTANT")
        )

    with contextlib.suppress(git.InvalidGitRepositoryError):
        if git.Repo(".").is_dirty():
            outcome = outcome.merge(
                Outcome.block("Working directory has uncommitted changes")
            )

    return outcome


@hook_handler(CanonicalHook.PRE_TOOL_USE)
def handle_pre_tool_use(hook: HookInputPreToolUse) -> Outcome:
    """Handle PreToolUse hook events.

    Args:
        hook: The hook input data.

    Returns:
        The merged Outcome for this tool call.
    """
    if hook.preToolUse is None:
        return Outcome()

    tool_name = hook.preToolUse.toolName

    if tool_name not in KNOWN_TOOLS:
        logger.debug("Ignoring unhandled tool: %s", tool_name)
        return Outcome()

    logger.info("Called %s", tool_name)

    TaskStateStore().clear_blocks(hook.taskId)

    plugins = load_plugins()
    outcome = _hook_result_outcome(
        CanonicalHook.PRE_TOOL_USE,
        plugins,
        hook.taskId,
        tool_name,
        parameters=hook.preToolUse.parameters,
        workspace_roots=hook.workspaceRoots,
        agent_type=hook.agentType,
    )

    handler = TOOL_HANDLERS.get((CanonicalHook.PRE_TOOL_USE, tool_name))
    if handler is not None:
        outcome = outcome.merge(handler(hook, hook.preToolUse, plugins))

    if outcome.disposition is Disposition.BLOCK:
        TaskStateStore().record_block(hook.taskId, tool_name, outcome.message or "")

    return outcome
