from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import bashlex
import bashlex.errors
import git

from cline_hooks.core.models import McpToolUse
from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.registry import hook_handler
from cline_hooks.core.response import allow, block
from cline_hooks.handlers.commands import (
    check_rules,
    contains_comment,
    extract_commands,
    extract_replacement_blocks,
    get_all_command_rules,
)
from cline_hooks.state.skills import (
    is_skill_called as _is_skill_called,
    required_skill_for,
)
from cline_hooks.state.store import TaskStateStore

try:
    from llm_prompts.install import get_managed_files as _get_managed_files_impl
except ImportError:
    _get_managed_files_impl = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputPreToolUse
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
    for managed_path in managed:
        if resolved.startswith(managed_path + "/"):
            return True
    return False


def _starts_with_emoji(text: str) -> bool:
    """Check if text starts with a non-ASCII character (emoji canary).

    Args:
        text: The text to check.

    Returns:
        True if the first non-whitespace character is non-ASCII.
    """
    stripped = text.lstrip()
    return bool(stripped) and ord(stripped[0]) > _EMOJI_THRESHOLD


def _apply_hook_result(
    hook_name: str,
    plugins: list[HooksPlugin],
    task_id: str,
    tool_name: str,
    **kwargs: object,
) -> None:
    """Collect plugin results and block or emit notes.

    Args:
        hook_name: The hook event name.
        plugins: Loaded plugin instances.
        task_id: The task identifier.
        tool_name: The tool being validated.
        **kwargs: Additional kwargs passed to on_hook.
    """
    result = collect_hook_results(plugins, hook_name, task_id=task_id, tool_name=tool_name, **kwargs)
    if result.block:
        block(result.block, task_id=task_id, tool_name=tool_name)
    if result.notes:
        allow("\n\n".join(result.notes))


@hook_handler("PreToolUse")
def handle_pre_tool_use(hook: HookInputPreToolUse) -> None:  # noqa: PLR0912, PLR0914, PLR0915
    """Handle PreToolUse hook events.

    Args:
        hook: The hook input data.
    """
    if hook.preToolUse is None:
        return

    tool_name = hook.preToolUse.toolName
    parameters = hook.preToolUse.parameters

    is_claude_code_mcp = "__" in tool_name
    if not is_claude_code_mcp and tool_name not in {
        "execute_command",
        "plan_mode_respond",
        "read_file",
        "replace_in_file",
        "use_mcp_tool",
        "write_to_file",
        "attempt_completion",
        "Bash",
        "Read",
        "Edit",
        "Write",
        "Skill",
    }:
        logger.debug("Ignoring unhandled tool: %s", tool_name)
        return

    logger.info("Called %s", tool_name)

    TaskStateStore().clear_blocks(hook.taskId)

    plugins = load_plugins()
    _apply_hook_result(
        "PreToolUse",
        plugins,
        hook.taskId,
        tool_name,
        parameters=parameters,
        workspace_roots=hook.workspaceRoots,
    )

    if tool_name == "plan_mode_respond":
        response: str = parameters.get("response", "")
        if not _starts_with_emoji(response):
            block(
                "Response does not start with an emoji - context window may be degraded. "
                "Use the new_task tool to start a fresh context.",
                task_id=hook.taskId,
                tool_name=tool_name,
            )

    elif tool_name == "read_file":
        path: str = parameters.get("path", "")
        if path:
            try:
                line_count = Path(path).read_text(encoding="utf-8", errors="replace").count("\n")
                if line_count > _LARGE_FILE_THRESHOLD:
                    block(
                        f"{path} is {line_count} lines. "
                        "Use a tool such as search_files with specific patterns instead of reading the whole file.",
                        task_id=hook.taskId,
                        tool_name=tool_name,
                    )
            except OSError:
                pass

    elif tool_name in {"execute_command", "Bash"}:
        command: str = parameters.get("command", "")
        if not command:
            return

        try:
            parsed = bashlex.parse(command)
        except bashlex.errors.ParsingError:
            logger.exception("Failed to parse command: %s", command)
            return

        violated_rule = check_rules(extract_commands(parsed), get_all_command_rules(plugins))
        if violated_rule:
            block(violated_rule.message, task_id=hook.taskId, tool_name=tool_name)

        required_skill = required_skill_for([cmd.name for cmd in extract_commands(parsed)])
        if required_skill and not _is_skill_called(hook.taskId, required_skill):
            block(
                f"Use the `{required_skill}` skill before running this command",
                task_id=hook.taskId,
                tool_name=tool_name,
            )

    elif tool_name in {"replace_in_file", "write_to_file", "Edit", "Write"}:
        file_path = parameters.get("path", "") or parameters.get("file_path", "")
        if file_path and _is_managed_path(file_path):
            block(
                f"{file_path} is managed by llm-prompts. "
                "Edit the source file instead, then run `llm-prompts update`.",
                task_id=hook.taskId,
                tool_name=tool_name,
            )

        diff = parameters.get("diff", "")
        if not diff:
            return

        replacement_blocks = extract_replacement_blocks(diff)
        logger.debug("block count: %s", len(replacement_blocks))

        notes: set[str] = set()

        for replacement_block in replacement_blocks:
            for line in replacement_block.split("\n"):
                if (stripped_line := line.strip()) and contains_comment(line):
                    logger.debug("comment in line: %s", stripped_line)
                    if "# type: ignore" in stripped_line and "ignore[" not in stripped_line:
                        notes.add(
                            "Avoid using type ignore comments where possible. If necessary, use specific ignores."
                        )
                    else:
                        notes.add(
                            "It is extremely important that you NEVER write comments explaining the "
                            "reasoning for a specific change. Comments should only be used to explain "
                            "complex code. If comments are required, consider a different approach."
                        )

        if notes:
            allow("\n\n".join(notes))

    elif tool_name == "use_mcp_tool":
        tool = McpToolUse(**parameters)
        _apply_hook_result(
            "PreMcpToolUse",
            plugins,
            hook.taskId,
            tool_name,
            mcp_tool_name=tool.tool_name,
            mcp_arguments=tool.arguments,
        )

    elif tool_name == "attempt_completion":
        task_progress: str = parameters.get("task_progress", "") or ""
        incomplete = [line for line in task_progress.splitlines() if line.strip().startswith("- [ ]")]
        if incomplete:
            block(
                f"task_progress has {len(incomplete)} incomplete item(s). Complete them before finishing.",
                task_id=hook.taskId,
                tool_name=tool_name,
            )

        result = collect_hook_results(plugins, "AttemptCompletion", task_id=hook.taskId)
        if result.notes:
            allow("\n\n".join(result.notes), prefix="IMPORTANT")

        try:
            repo = git.Repo(".")
            if repo.is_dirty():
                block(
                    "Working directory has uncommitted changes",
                    task_id=hook.taskId,
                    tool_name=tool_name,
                )
        except git.InvalidGitRepositoryError:
            pass
