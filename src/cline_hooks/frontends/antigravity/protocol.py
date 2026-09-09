"""Antigravity exit-code and JSON stdout protocol."""

from __future__ import annotations

import json
import sys
from typing import NoReturn

from cline_hooks.core.protocol import Protocol


class AntigravityProtocol(Protocol):
    """Antigravity JSON stdout protocol.

    - PreToolUse:
        Output: {"decision": "allow"} or {"decision": "deny", "reason": message}
    - PostToolUse:
        Output: {}
    - Stop:
        Output: {"decision": "continue", "reason": message} (to block stop and continue)
                or {"decision": "allow"} (to allow stop)
    """

    def __init__(self, hook_event_name: str = "PreToolUse") -> None:
        self._hook_event_name = hook_event_name

    def allow(self, message: str | None = None, *, system_message: str | None = None) -> NoReturn:  # noqa: ARG002
        """Allow the action or let the loop stop."""
        if self._hook_event_name == "PostToolUse":
            payload: dict[str, object] = {}
        elif self._hook_event_name == "Stop":
            payload = {"decision": "allow"}
        else:
            payload = {"decision": "allow"}
        print(json.dumps(payload), end="")
        sys.exit(0)

    def block(self, message: str) -> NoReturn:
        """Block tool execution or continue execution loop on Stop."""
        if self._hook_event_name == "Stop":
            payload: dict[str, object] = {"decision": "continue", "reason": message}
        elif self._hook_event_name == "PostToolUse":
            payload = {}
        else:
            payload = {"decision": "deny", "reason": message}
        print(json.dumps(payload), end="")
        sys.exit(0)

    def feedback(self, message: str) -> NoReturn:
        """Surfaces feedback; on Stop, this blocks termination and continues."""
        if self._hook_event_name == "Stop":
            payload: dict[str, object] = {"decision": "continue", "reason": message}
            print(json.dumps(payload), end="")
            sys.exit(0)
        self.block(message)

    def research_trace_header(self) -> str:
        """Return the instruction header prepended to a Stop research trace."""
        return (
            "RESEARCH TRACE: MUST cite lookups behind this turn's claims, in ONE "
            "line only: Sources: <tool> \"<detail>\", ..."
        )
