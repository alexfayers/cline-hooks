from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.vocabulary import CanonicalHook, PluginScope

if TYPE_CHECKING:
    import logging

_ORPHANED_NOTE = (
    "HANDBACK UNDELIVERABLE: the agent that spawned you has ended, so SubagentHandback cannot succeed and "
    "retrying will not help. Your report is kept as this call's message in your transcript, where cline-hooks' "
    "handback rescue reads it. Do not call SubagentHandback again; end your turn."
)


class HandbackRescuePlugin(HooksPlugin):
    """Surfaces a subagent report the harness withheld; tells an orphaned subagent to stop retrying."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Emit the subagent's own transcript report after a withheld handback, or a stop-retrying note.

        Args:
            hook_name: The hook event name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult carrying the rescued report or the stop-retrying note, otherwise None.
        """
        if hook_name == PluginScope.TOOL_FAILED:
            return HookResult(notes=[_ORPHANED_NOTE]) if kwargs.get("orphaned_handback") is True else None
        if hook_name != CanonicalHook.POST_TOOL_USE:
            return None
        agent_id = kwargs.get("withheld_report_agent_id")
        transcript_path = kwargs.get("transcript_path")
        if not isinstance(agent_id, str) or not agent_id or not isinstance(transcript_path, str) or not transcript_path:
            return None
        report = get_protocol().transcript.subagent_report(transcript_path, agent_id)
        if not report:
            return None
        logger.debug("Rescued withheld subagent report")
        header = f"RESCUED SUBAGENT REPORT (handback withheld by harness, agentId={agent_id}):"
        return HookResult(notes=[f"{header}\n{report}"])
