from __future__ import annotations

from cline_hooks.core.hook_kwargs import TrackToolUseKwargs
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.vocabulary import CanonicalHook, PluginScope
from cline_hooks.handlers.context_nudge import with_team_clause
from cline_hooks.state.plan import (
    consume_plan_nudge,
    is_plan_exit_tool,
    record_plan_exit,
)

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

    def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
        """Consume the pending handoff nudge, then record any plan exit.

        On the tool-tracking scope the pending nudge is consumed BEFORE the
        plan exit is recorded, so a plan-exit call arms the nudge for the next
        tool call rather than firing it on the same call.

        Args:
            hook_name: The hook event or plugin-scope name.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult carrying the nudge note, or None.
        """
        if hook_name == PluginScope.TRACK_TOOL_USE:
            kw = TrackToolUseKwargs.build(kwargs)
            result = _consumed_nudge(kw.task_id)
            if is_plan_exit_tool(kw.tool_name):
                record_plan_exit(kw.task_id)
            return result
        if hook_name == CanonicalHook.USER_PROMPT_SUBMIT:
            task_id = kwargs.get("task_id")
            if isinstance(task_id, str):
                return _consumed_nudge(task_id)
        return None
