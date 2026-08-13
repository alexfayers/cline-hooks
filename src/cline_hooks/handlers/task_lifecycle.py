from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import git
import git.exc

from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.registry import hook_handler
from cline_hooks.core.response import allow
from cline_hooks.handlers.git_context import get_git_context, resolve_tooling_notes
from cline_hooks.state.agents import reset as _reset_agents
from cline_hooks.state.context import reset as _reset_context
from cline_hooks.state.memory import reset as _reset_memory
from cline_hooks.state.plan import reset as _reset_plan
from cline_hooks.state.research import reset as _reset_research
from cline_hooks.state.skills import (
    _SKILL_REQUIREMENTS,
    reset as _reset_skills,
)
from cline_hooks.state.store import TaskStateStore
from cline_hooks.state.turns import reset as _reset_turns
from cline_hooks.state.workspace import (
    record_workspace,
    reset as reset_workspace,
)

if TYPE_CHECKING:
    from cline_hooks.core.models import (
        HookInputTaskCancel,
        HookInputTaskComplete,
        HookInputTaskResume,
        HookInputTaskStart,
    )
    from cline_hooks.state.store import TaskBlockEvent

logger = logging.getLogger("hooks")

_store = TaskStateStore()

_NO_RESET_SOURCES = frozenset({"resume", "compact"})


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
    source = hook.taskStart.source if hook.taskStart else ""
    if source not in _NO_RESET_SOURCES:
        _reset_skills(hook.taskId)
        _reset_memory(hook.taskId)
        _reset_turns(hook.taskId)
        _reset_agents(hook.taskId)
        _reset_context(hook.taskId)
        _reset_research(hook.taskId)
        _reset_plan(hook.taskId)
    parts: list[str] = []

    git_context = get_git_context(hook.workspaceRoots)
    if git_context:
        parts.append(git_context)

    plugins = load_plugins()

    parts.extend(resolve_tooling_notes(plugins, hook.workspaceRoots))
    record_workspace(hook.taskId, hook.workspaceRoots)

    result = collect_hook_results(
        plugins,
        "TaskStart",
        task_id=hook.taskId,
        workspace_roots=hook.workspaceRoots,
        source=source,
        agent_type=hook.agentType,
    )
    parts.extend(result.notes)

    system_message: str | None = None
    if result.user_notes and get_protocol().supports_user_message():
        system_message = "\n\n".join(n.user_text for n in result.user_notes)

    allow("\n\n".join(parts) or None, prefix="", system_message=system_message)


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
        pending_skills = {skill for block in blocks for skill in _SKILL_REQUIREMENTS.values() if skill in block.reason}
        if pending_skills:
            skills_list = ", ".join(f"`{s}`" for s in sorted(pending_skills))
            parts.append(f"REQUIRED: use the {skills_list} skill(s) before retrying the blocked command.")

    plugins = load_plugins()

    parts.extend(resolve_tooling_notes(plugins, hook.workspaceRoots))
    record_workspace(hook.taskId, hook.workspaceRoots)

    result = collect_hook_results(
        plugins,
        "TaskResume",
        task_id=hook.taskId,
        workspace_roots=hook.workspaceRoots,
    )
    parts.extend(result.notes)

    allow("\n\n".join(parts), prefix="")


@hook_handler("TaskCancel")
def handle_task_cancel(hook: HookInputTaskCancel) -> None:
    """Handle TaskCancel hook events.

    Args:
        hook: The hook input data.
    """
    parts: list[str] = []

    blocks = _store.get_blocks(hook.taskId)
    if blocks:
        parts.append(_format_block_history(blocks))

    result = collect_hook_results(load_plugins(), "TaskCancel", task_id=hook.taskId)
    parts.extend(result.notes)

    allow("\n\n".join(parts), prefix="")


@hook_handler("TaskComplete")
def handle_task_complete(hook: HookInputTaskComplete) -> None:
    """Handle TaskComplete hook events.

    Args:
        hook: The hook input data.
    """
    _store.clear_blocks(hook.taskId)
    _reset_memory(hook.taskId)
    _reset_turns(hook.taskId)
    _reset_agents(hook.taskId)
    _reset_context(hook.taskId)
    _reset_research(hook.taskId)
    _reset_plan(hook.taskId)
    reset_workspace(hook.taskId)
    collect_hook_results(load_plugins(), "TaskComplete", task_id=hook.taskId)
    allow()
