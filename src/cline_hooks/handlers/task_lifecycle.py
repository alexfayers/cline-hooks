from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import git
import git.exc

import cline_hooks.memory_tracker as _memory_tracker
from cline_hooks.git_context import get_git_context
from cline_hooks.plugin import load_plugins
from cline_hooks.registry import hook_handler
from cline_hooks.response import allow
from cline_hooks.skill_tracker import _SKILL_REQUIREMENTS, reset as _reset_skills
from cline_hooks.state import TaskStateStore

if TYPE_CHECKING:
    from cline_hooks.models import (
        HookInputTaskCancel,
        HookInputTaskComplete,
        HookInputTaskResume,
        HookInputTaskStart,
    )
    from cline_hooks.state import TaskBlockEvent

logger = logging.getLogger("hooks")

_store = TaskStateStore()


def _get_dirty_count(workspace_roots: list[str]) -> int | None:
    """Return the number of dirty files in the first valid git repo found.

    Args:
        workspace_roots: List of workspace root paths to search.

    Returns:
        Dirty file count, or None if no valid repo found.
    """
    for root in workspace_roots:
        try:
            repo = git.Repo(root)
            return len(repo.index.diff(None)) + len(repo.untracked_files)
        except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
            continue
    return None


def _format_block_history(blocks: list[TaskBlockEvent]) -> str:
    """Format a list of block events into a readable bullet list.

    Args:
        blocks: Block events to format.

    Returns:
        Multi-line string with one bullet per event.
    """
    lines = ["This task was previously interrupted. Block history:"]
    lines.extend(f"- [{b.timestamp}] {b.tool_name} blocked: {b.reason}" for b in blocks)
    return "\n".join(lines)


@hook_handler("TaskStart")
def handle_task_start(hook: HookInputTaskStart) -> None:
    """Handle TaskStart hook events.

    Args:
        hook: The hook input data.
    """
    _reset_skills(hook.taskId)
    _memory_tracker.clear(hook.taskId)
    parts: list[str] = []

    git_context = get_git_context(hook.workspaceRoots)
    if git_context:
        parts.append(git_context)

    for plugin in load_plugins():
        ctx = plugin.get_workspace_context(hook.workspaceRoots)
        if ctx:
            parts.append(ctx)

    workspace_name = Path(hook.workspaceRoots[0]).name if hook.workspaceRoots else None
    if workspace_name:
        parts.append(
            f"The project memory entity for this workspace is `project/{workspace_name}`."
        )

    parts.append(
        "REQUIRED before starting:\n"
        "1. `read_graph` on BOTH `memory-project` and `memory-global`\n"
        "2. `search_nodes` for task keywords in both servers\n"
        "3. `search_nodes` for `user-preferences` in `memory-global`\n"
        "4. `search_nodes` for `task/*` in `memory-project` (pending TODOs)\n"
        "5. `search_related_nodes` on any relevant result\n"
        "6. Include a `task_progress` checklist in your first tool call"
    )
    allow("\n\n".join(parts), prefix="")


@hook_handler("TaskResume")
def handle_task_resume(hook: HookInputTaskResume) -> None:
    """Handle TaskResume hook events.

    Args:
        hook: The hook input data.
    """
    parts: list[str] = []

    git_context = get_git_context(hook.workspaceRoots)
    if git_context:
        parts.append(git_context)

    blocks = _store.get_blocks(hook.taskId)
    if blocks:
        parts.append(_format_block_history(blocks))
        pending_skills = {
            skill
            for block in blocks
            for skill in _SKILL_REQUIREMENTS.values()
            if skill in block.reason
        }
        if pending_skills:
            skills_list = ", ".join(f"`{s}`" for s in sorted(pending_skills))
            parts.append(
                f"REQUIRED: use the {skills_list} skill(s) before retrying the blocked command."
            )

    workspace_name = Path(hook.workspaceRoots[0]).name if hook.workspaceRoots else None
    if workspace_name:
        parts.append(
            f"The project memory entity for this workspace is `project/{workspace_name}`."
        )

    allow("\n\n".join(parts), prefix="")


@hook_handler("TaskCancel")
def handle_task_cancel(hook: HookInputTaskCancel) -> None:
    """Handle TaskCancel hook events.

    Args:
        hook: The hook input data.
    """
    parts: list[str] = []

    dirty_count = _get_dirty_count(hook.workspaceRoots)
    if dirty_count:
        parts.append(
            f"Note: there are {dirty_count} uncommitted files in the working directory."
        )

    blocks = _store.get_blocks(hook.taskId)
    if blocks:
        parts.append(_format_block_history(blocks))

    parts.append(
        "REQUIRED:\n"
        "1. Update `memory-project` and `memory-global` now\n"
        "2. Record what was done, decisions made, and outstanding TODOs\n"
        "3. One observation per fact"
    )

    allow("\n\n".join(parts), prefix="")


@hook_handler("TaskComplete")
def handle_task_complete(hook: HookInputTaskComplete) -> None:
    """Handle TaskComplete hook events.

    Args:
        hook: The hook input data.
    """
    _store.clear_blocks(hook.taskId)
    allow()
