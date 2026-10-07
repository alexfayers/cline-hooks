from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cline_hooks.core.plugin import UserFacingNote, collect_hook_results, get_plugin_problems, load_plugins
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.registry import hook_handler
from cline_hooks.core.response import allow
from cline_hooks.core.vocabulary import NO_RESET_TASK_START_SOURCES, CanonicalHook
from cline_hooks.state.agents import reset as _reset_agents
from cline_hooks.state.finished import reset as _reset_finished
from cline_hooks.state.memory import reset as _reset_memory
from cline_hooks.state.skills import reset as _reset_skills
from cline_hooks.state.store import TaskStateStore
from cline_hooks.state.workspace import reset as reset_workspace

if TYPE_CHECKING:
    from cline_hooks.core.models import (
        HookInputTaskCancel,
        HookInputTaskComplete,
        HookInputTaskResume,
        HookInputTaskStart,
    )
    from cline_hooks.state.store import TaskBlockEvent

logger = logging.getLogger("hooks.task_lifecycle")

_store = TaskStateStore()


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


@hook_handler(CanonicalHook.TASK_START)
def handle_task_start(hook: HookInputTaskStart) -> None:
    """Handle TaskStart hook events.

    Args:
        hook: The hook input data.
    """
    source = hook.taskStart.source if hook.taskStart else ""
    if source not in NO_RESET_TASK_START_SOURCES:
        _reset_skills(hook.taskId)
        _reset_memory(hook.taskId)
        _reset_agents(hook.taskId)
        _reset_finished(hook.taskId)
    parts: list[str] = []

    result = collect_hook_results(
        load_plugins(),
        "TaskStart",
        task_id=hook.stateKey,
        workspace_roots=hook.workspaceRoots,
        source=source,
        agent_type=hook.agentType,
        agent_id=hook.agentId,
        is_teammate=hook.isTeammate,
    )
    if problems := get_plugin_problems():
        problem_note = "\n".join(["cline-hooks plugin problems:", *(f"- {problem}" for problem in problems)])
        result.notes.append(problem_note)
        result.user_notes.append(UserFacingNote(user_text=problem_note))
    parts.extend(result.notes)

    system_message: str | None = None
    if result.user_notes and get_protocol().supports_user_message():
        system_message = "\n\n".join(n.user_text for n in result.user_notes)

    allow("\n\n".join(parts) or None, prefix="", system_message=system_message)


@hook_handler(CanonicalHook.TASK_RESUME)
def handle_task_resume(hook: HookInputTaskResume) -> None:
    """Handle TaskResume hook events.

    Args:
        hook: The hook input data.
    """
    parts: list[str] = []

    blocks = _store.get_blocks(hook.taskId)
    if blocks:
        parts.append(_format_block_history(blocks))

    result = collect_hook_results(
        load_plugins(),
        "TaskResume",
        task_id=hook.stateKey,
        workspace_roots=hook.workspaceRoots,
        agent_type=hook.agentType,
        block_reasons=[block.reason for block in blocks],
        agent_id=hook.agentId,
        is_teammate=hook.isTeammate,
    )
    parts.extend(result.notes)

    allow("\n\n".join(parts), prefix="")


@hook_handler(CanonicalHook.TASK_CANCEL)
def handle_task_cancel(hook: HookInputTaskCancel) -> None:
    """Handle TaskCancel hook events.

    Args:
        hook: The hook input data.
    """
    parts: list[str] = []

    blocks = _store.get_blocks(hook.taskId)
    if blocks:
        parts.append(_format_block_history(blocks))

    result = collect_hook_results(
        load_plugins(),
        "TaskCancel",
        task_id=hook.stateKey,
        agent_id=hook.agentId,
        is_teammate=hook.isTeammate,
    )
    parts.extend(result.notes)

    allow("\n\n".join(parts), prefix="")


@hook_handler(CanonicalHook.TASK_COMPLETE)
def handle_task_complete(hook: HookInputTaskComplete) -> None:
    """Handle TaskComplete hook events.

    Args:
        hook: The hook input data.
    """
    _store.clear_blocks(hook.taskId)
    _reset_memory(hook.taskId)
    _reset_agents(hook.taskId)
    _reset_finished(hook.taskId)
    reset_workspace(hook.taskId)
    collect_hook_results(
        load_plugins(),
        "TaskComplete",
        task_id=hook.stateKey,
        agent_id=hook.agentId,
        is_teammate=hook.isTeammate,
    )
    allow()
