from __future__ import annotations

import contextlib
import logging
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

import git
import git.exc

from cline_hooks.core.models import McpToolUse
from cline_hooks.core.plugin import load_plugins
from cline_hooks.core.registry import hook_handler
from cline_hooks.core.response import allow
from cline_hooks.state.skills import record_skill as _record_skill

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputPostToolUse

logger = logging.getLogger("hooks")

_COMMIT_REMINDER = (
    "COMMIT REMINDER: There are a large number of uncommitted changes. "
    "Consider committing your work now to keep changes manageable."
)
_COMMIT_LINE_THRESHOLD = 200

_MEMORY_WRITE_TOOL_NAMES = {
    "create_entities",
    "create_relations",
    "add_observations",
    "delete_entity",
    "delete_relation",
    "delete_observations",
}


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


def handle_post_mcp_tool_use(tool: McpToolUse, task_id: str) -> None:
    """Handle post-MCP tool usage.

    Args:
        tool: The MCP tool invocation that completed.
        task_id: The Cline task identifier.
    """
    is_memory_write = tool.tool_name in _MEMORY_WRITE_TOOL_NAMES
    for plugin in load_plugins():
        note = plugin.on_post_tool_use(task_id, tool.tool_name, is_memory_write)
        if note:
            allow(note, prefix="")


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
        return

    if tool_name in {
        "replace_in_file",
        "write_to_file",
        "execute_command",
        "plan_mode_respond",
    }:
        for plugin in load_plugins():
            note = plugin.on_post_tool_use(hook.taskId, tool_name, is_memory_write=False)
            if note:
                allow(note, prefix="")

    if tool_name in {"replace_in_file", "write_to_file"}:
        diff_lines = _get_diff_line_count(hook.workspaceRoots)
        if diff_lines > _COMMIT_LINE_THRESHOLD:
            allow(
                f"{_COMMIT_REMINDER} ({diff_lines} lines changed)",
                prefix="",
            )

    if tool_name == "execute_command":
        result = hook.postToolUse.result
        if result and "BUILD FAILED" in result:
            allow("The build failed! It did NOT pass. It FAILED!!", prefix="")

    elif tool_name == "read_file":
        path = parameters.get("path", "")
        if path:
            file_path = PurePosixPath(path)
            if file_path.name == "SKILL.md":
                _record_skill(hook.taskId, file_path.parent.name)

    elif tool_name == "use_skill":
        skill_name = parameters.get("skill_name", "")
        if skill_name:
            _record_skill(hook.taskId, str(skill_name))

    elif tool_name == "use_mcp_tool":
        handle_post_mcp_tool_use(McpToolUse(**parameters), hook.taskId)
