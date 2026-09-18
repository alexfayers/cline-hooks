from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cline_hooks.core.hook_kwargs import TrackToolUseKwargs
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.state import PluginStateStore
from cline_hooks.core.vocabulary import (
    NO_RESET_TASK_START_SOURCES,
    PLAN_EXIT_TOOLS,
    CanonicalHook,
    PluginScope,
)
from cline_hooks.handlers.context_nudge import with_team_clause

if TYPE_CHECKING:
    import logging


@dataclass
class _PlanState:
    """Whether a plan-mode exit occurred this session, arming a pending nudge."""

    pending_nudge: bool = False


_store: PluginStateStore[_PlanState] = PluginStateStore("plan-state.json", _PlanState)


def is_plan_exit_tool(tool_name: str) -> bool:
    """Check whether a tool name marks the end of plan mode.

    Args:
        tool_name: The tool name as reported by the frontend.

    Returns:
        True if the tool signals a plan-mode exit.
    """
    return tool_name in PLAN_EXIT_TOOLS


def record_plan_exit(task_id: str) -> None:
    """Record that a plan-mode exit occurred this session.

    Arms a one-shot handoff nudge to be shown on the next user prompt.

    Args:
        task_id: The session or task identifier.
    """

    def mark(state: _PlanState) -> None:
        state.pending_nudge = True

    _store.update(task_id, mark)


def consume_plan_nudge(task_id: str) -> bool:
    """Return whether a pending plan-handoff nudge should fire, consuming it.

    Fires True at most once per recorded plan exit; subsequent calls return
    False until another plan exit is recorded.

    Args:
        task_id: The session or task identifier.

    Returns:
        True if a plan-handoff nudge is pending for this session.
    """

    def decide(state: _PlanState) -> bool:
        if not state.pending_nudge:
            return False
        state.pending_nudge = False
        return True

    return _store.update(task_id, decide)


def reset(task_id: str) -> None:
    """Clear the plan-exit record for a session.

    Args:
        task_id: The session or task identifier.
    """
    _store.reset(task_id)


_PLAN_HANDOFF_NUDGE = (
    "PLAN COMPLETE: A plan was just finalized this session. SHOULD hand off implementation to a fresh "
    "session so planning and full implementation do not consume one long context. MUST persist the plan to memory "
    "(rather than a heavy handoff doc) and capture any queued follow-on tasks as TODOs so a fresh session can "
    "pick up cleanly. MAY continue implementing here - this is a default, not a block."
)


def _consumed_nudge(task_id: str) -> HookResult | None:
    """Return the plan-handoff nudge if one is pending, consuming it.

    Args:
        task_id: The session or task identifier.

    Returns:
        A HookResult carrying the nudge note, or None when none is pending.
    """
    if consume_plan_nudge(task_id):
        return HookResult(notes=[with_team_clause(_PLAN_HANDOFF_NUDGE, task_id)])
    return None


class PlanHandoffPlugin(HooksPlugin):
    """Records plan-mode exits and emits a one-shot fresh-session handoff nudge."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Consume the pending handoff nudge, then record any plan exit.

        On the tool-tracking scope the pending nudge is consumed BEFORE the
        plan exit is recorded, so a plan-exit call arms the nudge for the next
        tool call rather than firing it on the same call.

        Args:
            hook_name: The hook event or plugin-scope name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult carrying the nudge note, or None.
        """
        if hook_name == PluginScope.TRACK_TOOL_USE:
            kw = TrackToolUseKwargs.build(kwargs)
            result = _consumed_nudge(kw.task_id)
            if result is not None:
                logger.debug("Fired plan-handoff nudge")
            if is_plan_exit_tool(kw.tool_name):
                record_plan_exit(kw.task_id)
            return result
        if hook_name == CanonicalHook.USER_PROMPT_SUBMIT:
            task_id = kwargs.get("task_id")
            if isinstance(task_id, str):
                result = _consumed_nudge(task_id)
                if result is not None:
                    logger.debug("Fired plan-handoff nudge")
                return result
            return None
        if hook_name == CanonicalHook.TASK_START:
            task_id = kwargs.get("task_id")
            source = kwargs.get("source")
            if isinstance(task_id, str) and source not in NO_RESET_TASK_START_SOURCES:
                reset(task_id)
            return None
        if hook_name == CanonicalHook.TASK_COMPLETE:
            task_id = kwargs.get("task_id")
            if isinstance(task_id, str):
                reset(task_id)
            return None
        return None
