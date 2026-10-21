"""Codex hook protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cline_hooks.core.frontend import EXACT_MATCH, frontend
from cline_hooks.core.protocol import Protocol
from cline_hooks.core.transcript import NULL_TRANSCRIPT
from cline_hooks.frontends.claude_code.protocol import ClaudeCodeProtocol
from cline_hooks.frontends.codex.install import CodexInstaller

if TYPE_CHECKING:
    from cline_hooks.core.outcome import Outcome
    from cline_hooks.core.protocol import RawPayload
    from cline_hooks.core.response import Response
    from cline_hooks.core.transcript import TranscriptReader

_PLAIN_OUTPUT_EVENTS = frozenset({"Stop", "SubagentStop"})


@frontend(name="codex", display_name="Codex", installer=CodexInstaller(), detect_priority=EXACT_MATCH)
class CodexProtocol(ClaudeCodeProtocol):
    """Codex hook protocol.

    Codex reuses Claude Code's hook JSON shape, native tool names and output
    JSON, so it inherits `ClaudeCodeProtocol`. It differs in the `turn_id` key
    every event except SessionStart carries, in dropping `updatedInput`, in
    taking the plain exit-code contract on Stop and SubagentStop, and in a
    transcript format cline-hooks does not read. A Codex SessionStart carries
    no `turn_id`, so it is handled as Claude Code.
    """

    transcript: ClassVar[TranscriptReader] = NULL_TRANSCRIPT

    @classmethod
    def detect(cls, payload: RawPayload) -> bool:
        """Detect an event carrying Codex's `turn_id` key.

        Returns:
            True for a registered event whose payload has a `turn_id`.
        """
        data = payload.data
        return isinstance(data, dict) and data.get(cls.hook_event_key) in cls.native_hook_names() and "turn_id" in data

    def supports_updated_input(self) -> bool:
        """Codex rejects `updatedInput` without a permission decision.

        Returns:
            False, always.
        """
        return False

    def render(self, outcome: Outcome) -> Response:
        """Render the outcome as Claude Code does, except Stop and SubagentStop.

        Codex's Stop and SubagentStop outputs carry no `hookSpecificOutput`,
        so those events use the plain exit-code contract.

        Returns:
            The rendered Response.
        """
        if self._hook_event_name in _PLAIN_OUTPUT_EVENTS:
            return Protocol.render(self, outcome)
        return super().render(outcome)
