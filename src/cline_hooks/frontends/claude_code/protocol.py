# ruff: noqa: T201
"""Claude Code exit-code protocol."""

from __future__ import annotations

import json
import sys
from typing import NoReturn

from cline_hooks.frontends.kiro.protocol import KiroProtocol


class ClaudeCodeProtocol(KiroProtocol):
    """Claude Code exit-code protocol.

    Same block as Kiro, but allow/feedback context uses
    hookSpecificOutput.additionalContext (exit 0) instead of plain stdout or
    exit 2, since Claude Code only surfaces plain stdout to the model for
    UserPromptSubmit/UserPromptExpansion/SessionStart - every other event
    needs additionalContext to actually reach the model.
    """

    def __init__(self, hook_event_name: str = "Stop") -> None:
        """Store the raw Claude Code hook event name for context injection.

        Args:
            hook_event_name: The raw hook_event_name from the incoming
                payload (not the remapped internal hookName), so the
                emitted hookSpecificOutput.hookEventName is always a valid
                Claude Code event name.
        """
        self._hook_event_name = hook_event_name

    def _print_additional_context(self, message: str) -> None:
        """Print a hookSpecificOutput.additionalContext payload for the current event."""
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": self._hook_event_name,
                        "additionalContext": message,
                    },
                },
            ),
            end="",
        )

    def supports_user_message(self) -> bool:
        """Claude Code surfaces a top-level systemMessage directly to the user.

        Returns:
            True, since Claude Code has a direct-to-user channel.
        """
        return True

    def allow(self, message: str | None = None, *, system_message: str | None = None) -> NoReturn:
        """Continue via exit 0, context in hookSpecificOutput and/or systemMessage."""
        payload: dict[str, object] = {}
        if system_message is not None:
            payload["systemMessage"] = system_message
        if message is not None:
            payload["hookSpecificOutput"] = {
                "hookEventName": self._hook_event_name,
                "additionalContext": message,
            }
        if payload:
            print(json.dumps(payload), end="")
        sys.exit(0)

    def feedback(self, message: str) -> NoReturn:
        """Continue via exit 0, non-error context in hookSpecificOutput."""
        self._print_additional_context(message)
        sys.exit(0)

    def research_trace_header(self) -> str:
        """Return the Stop research-trace header for Claude Code.

        Claude Code surfaces this hook's raw additionalContext output to the
        user directly, so the model's reply can stay a single terse line.
        """
        return (
            "RESEARCH TRACE: cite lookups behind this turn's claims. Reply with ONE "
            "line only - the user already sees this hook's raw output."
        )
