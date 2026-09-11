from __future__ import annotations

import contextlib
import logging
from pathlib import PurePosixPath
import re
from typing import TYPE_CHECKING, Any

import git
import git.exc

from cline_hooks.core.outcome import Outcome
from cline_hooks.core.parameters import (
    McpToolUse,
    ReadParameters,
    ShellParameters,
    SkillParameters,
    WebResearchParameters,
)
from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.registry import TOOL_HANDLERS, hook_handler, tool_handler
from cline_hooks.core.vocabulary import (
    CanonicalHook,
    CanonicalTool,
    FILE_EDIT_TOOLS,
    SHELL_TOOLS,
    WEB_RESEARCH_TOOLS,
)
from cline_hooks.handlers.context_nudge import context_note, with_team_clause
from cline_hooks.handlers.git_context import resolve_tooling_notes
from cline_hooks.handlers.user_prompt import _PLAN_HANDOFF_NUDGE
from cline_hooks.state.agents import (
    is_agent_tool as _is_agent_tool,
    record_agent_use as _record_agent_use,
)
from cline_hooks.state.memory import (
    has_memory_writes as _has_memory_writes,
    is_memory_write as _is_memory_write,
    record_memory_write as _record_memory_write,
)
from cline_hooks.state.plan import (
    consume_plan_nudge as _consume_plan_nudge,
    is_plan_exit_tool as _is_plan_exit_tool,
    record_plan_exit as _record_plan_exit,
)
import cline_hooks.state.research as research_state
from cline_hooks.state.retrospective import record_session as _record_retro_session
from cline_hooks.state.skills import record_skill as _record_skill
from cline_hooks.state.workspace import should_note_workspace_change

if TYPE_CHECKING:
    from collections.abc import Callable

    from cline_hooks.core.models import HookInputPostToolUse, PostToolUseFields
    from cline_hooks.core.plugin import HooksPlugin

logger = logging.getLogger("hooks")

_SKILL_MD_PATH = re.compile(r"([\w.-]+)/SKILL\.md\b")

_COMMIT_REMINDER = (
    "COMMIT REMINDER: There are a large number of uncommitted changes. "
    "SHOULD commit your work now to keep changes manageable."
)
_COMMIT_LINE_THRESHOLD = 200

_MEMORY_WARNING = (
    "WARNING: No memory writes have been made this session. "
    "You MUST persist your work to memory NOW before completing. "
    "Knowledge not persisted is permanently lost."
)

_WRAP_UP_SKILLS = frozenset({"session-end", "handoff"})
_RETRO_THRESHOLD = 5
_RETRO_REMINDER = (
    "You have completed {count} sessions since your last /retrospective. "
    "SHOULD run it to capture learnings across recent sessions."
)


def _get_all_state_write_tool_names(plugins: list[HooksPlugin]) -> frozenset[str]:
    """Collect state-write tool names from all plugins.

    Args:
        plugins: Loaded plugin instances.

    Returns:
        Union of all plugin state-write tool name sets.
    """
    names: set[str] = set()
    for plugin in plugins:
        names.update(plugin.get_state_write_tool_names())
    return frozenset(names)


def _get_all_research_tool_names(plugins: list[HooksPlugin]) -> frozenset[str]:
    """Collect research lookup tool names from all plugins.

    Args:
        plugins: Loaded plugin instances.

    Returns:
        Union of the default research tools and all plugin research tool sets.
    """
    names: set[str] = set(WEB_RESEARCH_TOOLS)
    for plugin in plugins:
        names.update(plugin.get_research_tool_names())
    return frozenset(names)


def _get_all_research_detail_extractors(
    plugins: list[HooksPlugin],
) -> dict[str, Callable[[dict[str, Any]], str]]:
    """Collect research detail extractors from all plugins.

    Later plugins override earlier ones on key collision.

    Args:
        plugins: Loaded plugin instances.

    Returns:
        Merged mapping of tool name to detail-extraction callable.
    """
    extractors: dict[str, Callable[[dict[str, Any]], str]] = {}
    for plugin in plugins:
        extractors.update(plugin.get_research_detail_extractors())
    return extractors


def _extract_research_detail(
    tool_name: str,
    parameters: dict[str, Any],
    extractors: dict[str, Callable[[dict[str, Any]], str]],
) -> str:
    """Return a short identifier for a research lookup.

    A plugin-supplied extractor for the tool takes precedence; extractors are
    third-party plugin code, so failures are caught and treated as no detail.
    Falls back to the built-in WebFetch/WebSearch handling.

    Args:
        tool_name: The research tool name.
        parameters: The tool parameters.
        extractors: Per-tool detail extractors contributed by plugins.

    Returns:
        A URL for WebFetch, a query for WebSearch, an extractor-derived string,
        otherwise an empty string.
    """
    extractor = extractors.get(tool_name)
    if extractor is not None:
        try:
            detail = extractor(parameters)
        except Exception:
            logger.exception("Research detail extractor for %s failed", tool_name)
            return ""
        return str(detail or "")
    if tool_name in WEB_RESEARCH_TOOLS:
        params = WebResearchParameters.build(parameters)
        return str(params.url if tool_name == CanonicalTool.WEB_FETCH else params.query)
    return ""


def _parse_diff_stat_line(line: str) -> int:
    """Extract inserted+deleted line count from a single git diff --stat output line.

    Args:
        line: A single line from git diff --stat output.

    Returns:
        Total line count for this stat line.
    """
    total = 0
    for part in line.split(","):
        stripped = part.strip()
        if "insertion" in stripped or "deletion" in stripped:
            with contextlib.suppress(ValueError, IndexError):
                total += int(stripped.split()[0])
    return total


def _get_diff_line_count(workspace_roots: list[str]) -> int:
    """Return total added+removed lines in the working tree of the first valid repo.

    Args:
        workspace_roots: Workspace root paths to search for a git repo.

    Returns:
        Total diff line count, or 0 if no repo or no diff.
    """
    for root in workspace_roots:
        try:
            repo = git.Repo(root)
            diff = repo.git.diff("--stat", "HEAD")
        except (
            git.exc.InvalidGitRepositoryError,
            git.exc.GitCommandError,
            git.exc.NoSuchPathError,
        ):
            continue
        else:
            return sum(_parse_diff_stat_line(line) for line in diff.splitlines())
    return 0


def _skills_in_command(command: str) -> list[str]:
    """Return skill names referenced by SKILL.md paths inside a shell command.

    Args:
        command: The shell command string.

    Returns:
        Skill names whose SKILL.md is read by the command (e.g. via cat/sed).
    """
    return _SKILL_MD_PATH.findall(command)


def _record_skill_use(task_id: str, tool_name: str, parameters: dict[str, Any]) -> None:
    """Record any skill loaded by a tool call.

    Skills load via the canonical skill tool, a read of a SKILL.md file, or a
    shell command that reads one.

    Args:
        task_id: The session or task identifier.
        tool_name: The tool name as reported by the frontend.
        parameters: The tool parameters.
    """
    if tool_name == CanonicalTool.SKILL:
        skill_name = str(SkillParameters.build(parameters).skill)
        if skill_name:
            _record_skill(task_id, skill_name)
    elif tool_name == CanonicalTool.READ:
        path = ReadParameters.build(parameters).path
        if path:
            file_path = PurePosixPath(path)
            if file_path.name == "SKILL.md":
                _record_skill(task_id, file_path.parent.name)
    elif tool_name in SHELL_TOOLS:
        for skill_name in _skills_in_command(
            str(ShellParameters.build(parameters).command)
        ):
            _record_skill(task_id, skill_name)


def _is_skill_invocation(
    tool_name: str, parameters: dict[str, Any], skill_names: frozenset[str]
) -> bool:
    """Check whether the current tool call invokes one of the given skills.

    Covers every way a skill loads: the Skill/use_skill tools, a Read of a
    SKILL.md file, or a shell command that reads a SKILL.md file.

    Args:
        tool_name: The tool name as reported by the frontend.
        parameters: The tool parameters.
        skill_names: The skill names to match against.

    Returns:
        True if the tool call invokes any of the given skills.
    """
    if tool_name == CanonicalTool.SKILL:
        return SkillParameters.build(parameters).skill in skill_names
    if tool_name == CanonicalTool.READ:
        path = ReadParameters.build(parameters).path
        return any(path.endswith(f"{name}/SKILL.md") for name in skill_names)
    if tool_name in SHELL_TOOLS:
        loaded = _skills_in_command(str(ShellParameters.build(parameters).command))
        return any(name in loaded for name in skill_names)
    return False


def _is_session_end_skill(tool_name: str, parameters: dict[str, object]) -> bool:
    """Check whether the current tool call is invoking the session-end skill.

    Args:
        tool_name: The tool name as reported by the frontend.
        parameters: The tool parameters.

    Returns:
        True if this is a session-end skill invocation.
    """
    return _is_skill_invocation(tool_name, parameters, frozenset({"session-end"}))


def _is_wrap_up_skill(tool_name: str, parameters: dict[str, object]) -> bool:
    """Check whether the current tool call invokes a session wrap-up skill.

    Args:
        tool_name: The tool name as reported by the frontend.
        parameters: The tool parameters.

    Returns:
        True if this is a session-end or handoff skill invocation.
    """
    return _is_skill_invocation(tool_name, parameters, _WRAP_UP_SKILLS)


def _record_tool_use(  # noqa: PLR0913, PLR0917
    task_id: str,
    tool_name: str,
    parameters: dict[str, Any],
    state_write_names: frozenset[str],
    research_names: frozenset[str],
    extractors: dict[str, Callable[[dict[str, Any]], str]],
) -> tuple[bool, str | None]:
    """Record memory/skill/agent/research use for a tool call and resolve its MCP identity.

    Args:
        task_id: The session or task identifier.
        tool_name: The tool name as reported by the frontend.
        parameters: The tool parameters.
        state_write_names: Tool names that count as plugin state writes.
        research_names: Tool names that count as research lookups.
        extractors: Per-tool research detail extractors contributed by plugins.

    Returns:
        A tuple of (is_state_write, mcp_tool_name).
    """
    mcp_tool_name: str | None = None
    arguments = parameters
    if tool_name == CanonicalTool.MCP:
        tool = McpToolUse.build(parameters)
        mcp_tool_name = tool.tool_name
        arguments = tool.arguments
        if _is_memory_write(tool.tool_name):
            _record_memory_write(task_id, tool.tool_name)
    else:
        _record_skill_use(task_id, tool_name, parameters)

    is_state_write = mcp_tool_name is not None and mcp_tool_name in state_write_names

    if _is_agent_tool(tool_name):
        _record_agent_use(task_id, tool_name)

    if _is_plan_exit_tool(tool_name):
        _record_plan_exit(task_id)

    research_tool = mcp_tool_name or tool_name
    if research_state.is_research_tool(research_tool, research_names):
        detail = _extract_research_detail(research_tool, arguments, extractors)
        research_state.record_research(task_id, research_tool, detail)

    return is_state_write, mcp_tool_name


def _workspace_change_outcome(
    hook: HookInputPostToolUse, plugins: list[HooksPlugin]
) -> Outcome:
    """Build the ecosystem tooling guidance outcome for a workspace root change.

    Args:
        hook: The hook input data.
        plugins: Loaded plugin instances.

    Returns:
        An ALLOW Outcome with the tooling note, or an empty Outcome if the
        working directory hasn't changed or there's no note to show.
    """
    if not should_note_workspace_change(hook.taskId, hook.workspaceRoots):
        return Outcome()
    notes = resolve_tooling_notes(plugins, hook.workspaceRoots)
    if not notes:
        return Outcome()
    return Outcome.allow(
        f"Working directory changed to {hook.workspaceRoots[0]}. " + "\n\n".join(notes),
        label="REMINDER",
    )


@tool_handler(CanonicalHook.POST_TOOL_USE, *FILE_EDIT_TOOLS)
def _post_file_edit(
    hook: HookInputPostToolUse, _fields: PostToolUseFields, _plugins: list[HooksPlugin]
) -> Outcome:
    """Remind to commit when a large amount of uncommitted diff has accumulated.

    Args:
        hook: The hook input data.
        _fields: The PostToolUse fields (unused).
        _plugins: Loaded plugin instances (unused).

    Returns:
        An ALLOW Outcome with a commit reminder if the diff exceeds the
        commit-line threshold, otherwise an empty Outcome.
    """
    diff_lines = _get_diff_line_count(hook.workspaceRoots)
    if diff_lines > _COMMIT_LINE_THRESHOLD:
        return Outcome.allow(f"{_COMMIT_REMINDER} ({diff_lines} lines changed)")
    return Outcome()


@tool_handler(CanonicalHook.POST_TOOL_USE, *SHELL_TOOLS)
def _post_shell(
    _hook: HookInputPostToolUse, fields: PostToolUseFields, _plugins: list[HooksPlugin]
) -> Outcome:
    """Alert when a shell command's result reports a build failure.

    Args:
        _hook: The hook input data (unused).
        fields: The PostToolUse fields.
        _plugins: Loaded plugin instances (unused).

    Returns:
        An ALLOW Outcome alerting on a build failure, otherwise an empty Outcome.
    """
    if fields.result and "BUILD FAILED" in fields.result:
        return Outcome.allow("The build failed! It did NOT pass. It FAILED!!")
    return Outcome()


@hook_handler(CanonicalHook.POST_TOOL_USE)
def handle_post_tool_use(hook: HookInputPostToolUse) -> Outcome:
    """Handle PostToolUse hook events.

    Args:
        hook: The hook input data.

    Returns:
        The merged Outcome for this tool call.
    """
    if hook.postToolUse is None:
        return Outcome()

    tool_name = hook.postToolUse.toolName
    parameters = hook.postToolUse.parameters

    logger.info("Called %s", tool_name)

    if not hook.postToolUse.success:
        logger.warning("Tool %s failed", tool_name)
        return Outcome.allow(
            "A tool just failed. When you fix this, MUST persist what went wrong and the fix "
            "to memory (and to rules/skills where it reveals a missing process step)."
        )

    plan_nudge_pending = _consume_plan_nudge(hook.taskId)

    plugins = load_plugins()
    state_write_names = _get_all_state_write_tool_names(plugins)
    research_names = _get_all_research_tool_names(plugins)
    extractors = _get_all_research_detail_extractors(plugins)

    is_state_write, mcp_tool_name = _record_tool_use(
        hook.taskId,
        tool_name,
        parameters,
        state_write_names,
        research_names,
        extractors,
    )

    retro_count = (
        _record_retro_session(hook.taskId)
        if _is_wrap_up_skill(tool_name, parameters)
        else None
    )

    result = collect_hook_results(
        plugins,
        CanonicalHook.POST_TOOL_USE,
        task_id=hook.taskId,
        tool_name=tool_name,
        parameters=hook.postToolUse.parameters,
        is_state_write=is_state_write,
        mcp_tool_name=mcp_tool_name,
        workspace_roots=hook.workspaceRoots,
        agent_type=hook.agentType,
    )

    outcome = Outcome()
    if result.notes:
        outcome = outcome.merge(Outcome.allow("\n\n".join(result.notes)))

    handler = TOOL_HANDLERS.get((CanonicalHook.POST_TOOL_USE, tool_name))
    if handler is not None:
        outcome = outcome.merge(handler(hook, hook.postToolUse, plugins))

    messages: list[str] = []
    if _is_session_end_skill(tool_name, parameters) and not _has_memory_writes(
        hook.taskId
    ):
        messages.append(_MEMORY_WARNING)
    if retro_count is not None and retro_count >= _RETRO_THRESHOLD:
        messages.append(_RETRO_REMINDER.format(count=retro_count))
    if plan_nudge_pending:
        messages.append(with_team_clause(_PLAN_HANDOFF_NUDGE, hook.taskId))
    if hook.transcriptPath:
        token_count = get_protocol().transcript.context_tokens(hook.transcriptPath)
        if token_count is not None:
            note = context_note(hook.taskId, token_count)
            if note is not None:
                messages.append(note)
    if messages:
        outcome = outcome.merge(Outcome.allow("\n\n".join(messages)))

    if not outcome.notes:
        outcome = outcome.merge(_workspace_change_outcome(hook, plugins))

    return outcome
