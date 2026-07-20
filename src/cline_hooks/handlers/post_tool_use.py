from __future__ import annotations

import contextlib
import logging
from pathlib import PurePosixPath
import re
from typing import TYPE_CHECKING, Any

import git
import git.exc

from cline_hooks.core.models import McpToolUse
from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.registry import hook_handler
from cline_hooks.core.response import allow
from cline_hooks.state.agents import (
    is_agent_tool as _is_agent_tool,
    record_agent_use as _record_agent_use,
)
from cline_hooks.state.memory import (
    has_memory_writes as _has_memory_writes,
    is_memory_write as _is_memory_write,
    record_memory_write as _record_memory_write,
)
from cline_hooks.state.retrospective import record_session as _record_retro_session
from cline_hooks.state.skills import record_skill as _record_skill

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputPostToolUse
    from cline_hooks.core.plugin import HooksPlugin

logger = logging.getLogger("hooks")

_SHELL_TOOL_NAMES = frozenset({"execute_command", "Bash"})
_SKILL_MD_PATH = re.compile(r"([\w.-]+)/SKILL\.md\b")

_COMMIT_REMINDER = (
    "COMMIT REMINDER: There are a large number of uncommitted changes. "
    "Consider committing your work now to keep changes manageable."
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
    "Consider running it to capture learnings across recent sessions."
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
        except (git.exc.InvalidGitRepositoryError, git.exc.GitCommandError, git.exc.NoSuchPathError):
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

    Skills load in several ways depending on the frontend: the Skill/use_skill
    tools, a Read of a SKILL.md file, or a shell command that reads a SKILL.md
    file (e.g. Codex reading it via cat/sed).

    Args:
        task_id: The session or task identifier.
        tool_name: The tool name as reported by the frontend.
        parameters: The tool parameters.
    """
    if tool_name == "use_skill":
        skill_name = str(parameters.get("skill_name", ""))
        if skill_name:
            _record_skill(task_id, skill_name)
    elif tool_name == "Skill":
        skill_name = str(parameters.get("skill", ""))
        if skill_name:
            _record_skill(task_id, skill_name)
    elif tool_name in {"read_file", "Read"}:
        path = parameters.get("path", "") or parameters.get("file_path", "")
        if path:
            file_path = PurePosixPath(str(path))
            if file_path.name == "SKILL.md":
                _record_skill(task_id, file_path.parent.name)
    elif tool_name in _SHELL_TOOL_NAMES:
        for skill_name in _skills_in_command(str(parameters.get("command", ""))):
            _record_skill(task_id, skill_name)


def _is_skill_invocation(tool_name: str, parameters: dict[str, object], skill_names: frozenset[str]) -> bool:
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
    if tool_name == "Skill":
        return parameters.get("skill") in skill_names
    if tool_name == "use_skill":
        return parameters.get("skill_name") in skill_names
    if tool_name in {"read_file", "Read"}:
        path = str(parameters.get("path", "") or parameters.get("file_path", ""))
        return any(path.endswith(f"{name}/SKILL.md") for name in skill_names)
    if tool_name in _SHELL_TOOL_NAMES:
        loaded = _skills_in_command(str(parameters.get("command", "")))
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


def _record_tool_use(
    task_id: str,
    tool_name: str,
    parameters: dict[str, Any],
    state_write_names: frozenset[str],
) -> tuple[bool, str | None]:
    """Record memory/skill/agent use for a tool call and resolve its MCP identity.

    Args:
        task_id: The session or task identifier.
        tool_name: The tool name as reported by the frontend.
        parameters: The tool parameters.
        state_write_names: Tool names that count as plugin state writes.

    Returns:
        A tuple of (is_state_write, mcp_tool_name).
    """
    is_state_write = False
    mcp_tool_name: str | None = None
    if tool_name == "use_mcp_tool":
        tool = McpToolUse(**parameters)
        mcp_tool_name = tool.tool_name
        is_state_write = tool.tool_name in state_write_names
        if _is_memory_write(tool.tool_name):
            _record_memory_write(task_id, tool.tool_name)
    elif _is_memory_write(tool_name):
        _record_memory_write(task_id, tool_name)
        if "__" in tool_name:
            mcp_tool_name = tool_name.rsplit("__", 1)[-1]
            is_state_write = mcp_tool_name in state_write_names
    else:
        _record_skill_use(task_id, tool_name, parameters)

    if _is_agent_tool(tool_name):
        _record_agent_use(task_id, tool_name)

    return is_state_write, mcp_tool_name


@hook_handler("PostToolUse")
def handle_post_tool_use(hook: HookInputPostToolUse) -> None:
    """Handle PostToolUse hook events.

    Args:
        hook: The hook input data.
    """
    if hook.postToolUse is None:
        return

    tool_name = hook.postToolUse.toolName
    parameters = hook.postToolUse.parameters

    logger.info("Called %s", tool_name)

    if not hook.postToolUse.success:
        logger.warning("Tool %s failed", tool_name)
        allow(
            "A tool just failed. When you fix this, persist what went wrong and the fix "
            "to memory (and to rules/skills if it reveals a missing process step).",
            prefix="",
        )
        return

    plugins = load_plugins()
    state_write_names = _get_all_state_write_tool_names(plugins)

    is_state_write, mcp_tool_name = _record_tool_use(hook.taskId, tool_name, parameters, state_write_names)

    retro_count = _record_retro_session(hook.taskId) if _is_wrap_up_skill(tool_name, parameters) else None

    result = collect_hook_results(
        plugins,
        "PostToolUse",
        task_id=hook.taskId,
        tool_name=tool_name,
        parameters=hook.postToolUse.parameters,
        is_state_write=is_state_write,
        mcp_tool_name=mcp_tool_name,
        workspace_roots=hook.workspaceRoots,
        agent_type=hook.agentType,
    )
    if result.notes:
        allow("\n\n".join(result.notes), prefix="")

    if tool_name in {"replace_in_file", "write_to_file"}:
        diff_lines = _get_diff_line_count(hook.workspaceRoots)
        if diff_lines > _COMMIT_LINE_THRESHOLD:
            allow(
                f"{_COMMIT_REMINDER} ({diff_lines} lines changed)",
                prefix="",
            )

    if tool_name == "execute_command":
        result_text = hook.postToolUse.result
        if result_text and "BUILD FAILED" in result_text:
            allow("The build failed! It did NOT pass. It FAILED!!", prefix="")

    messages: list[str] = []
    if _is_session_end_skill(tool_name, parameters) and not _has_memory_writes(hook.taskId):
        messages.append(_MEMORY_WARNING)
    if retro_count is not None and retro_count >= _RETRO_THRESHOLD:
        messages.append(_RETRO_REMINDER.format(count=retro_count))
    if messages:
        allow("\n\n".join(messages), prefix="")
