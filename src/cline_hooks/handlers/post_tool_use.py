from __future__ import annotations

import contextlib
import logging
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import git
import git.exc

from cline_hooks.core.models import McpToolUse
from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.registry import hook_handler
from cline_hooks.core.response import allow
from cline_hooks.state.memory import (
    has_memory_writes as _has_memory_writes,
    is_memory_write as _is_memory_write,
    record_memory_write as _record_memory_write,
)
from cline_hooks.state.skills import record_skill as _record_skill

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputPostToolUse
    from cline_hooks.core.plugin import HooksPlugin

logger = logging.getLogger("hooks")

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


def _is_session_end_skill(tool_name: str, parameters: dict[str, object]) -> bool:
    """Check whether the current tool call is invoking the session-end skill.

    Args:
        tool_name: The tool name as reported by the frontend.
        parameters: The tool parameters.

    Returns:
        True if this is a session-end skill invocation.
    """
    if tool_name == "Skill":
        return parameters.get("skill") == "session-end"
    if tool_name == "use_skill":
        return parameters.get("skill_name") == "session-end"
    if tool_name in {"read_file", "Read"}:
        path = str(parameters.get("path", "") or parameters.get("file_path", ""))
        return path.endswith("session-end/SKILL.md")
    return False


@hook_handler("PostToolUse")
def handle_post_tool_use(hook: HookInputPostToolUse) -> None:  # noqa: PLR0912
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

    is_state_write = False
    mcp_tool_name: str | None = None
    if tool_name == "use_mcp_tool":
        tool = McpToolUse(**parameters)
        mcp_tool_name = tool.tool_name
        is_state_write = tool.tool_name in state_write_names
        if _is_memory_write(tool.tool_name):
            _record_memory_write(hook.taskId, tool.tool_name)
    elif _is_memory_write(tool_name):
        _record_memory_write(hook.taskId, tool_name)
    elif tool_name == "use_skill":
        skill_name = parameters.get("skill_name", "")
        if skill_name:
            _record_skill(hook.taskId, str(skill_name))
    elif tool_name == "Skill":
        skill_name = parameters.get("skill", "")
        if skill_name:
            _record_skill(hook.taskId, str(skill_name))
    elif tool_name in {"read_file", "Read"}:
        path = parameters.get("path", "") or parameters.get("file_path", "")
        if path:
            file_path = PurePosixPath(path)
            if file_path.name == "SKILL.md":
                _record_skill(hook.taskId, file_path.parent.name)

    result = collect_hook_results(
        plugins,
        "PostToolUse",
        task_id=hook.taskId,
        tool_name=tool_name,
        parameters=hook.postToolUse.parameters,
        is_state_write=is_state_write,
        mcp_tool_name=mcp_tool_name,
        workspace_roots=hook.workspaceRoots,
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

    if _is_session_end_skill(tool_name, parameters) and not _has_memory_writes(hook.taskId):
        allow(_MEMORY_WARNING, prefix="")
