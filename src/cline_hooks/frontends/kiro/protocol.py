# ruff: noqa: T201
"""Kiro exit-code protocol."""

from __future__ import annotations

import json
import sys
from typing import NoReturn

from cline_hooks.core.protocol import Protocol


class KiroProtocol(Protocol):
    """Kiro exit-code protocol: exit 0 + stdout for allow, exit 2 + stderr for block."""

    def allow(self, message: str | None = None, *, system_message: str | None = None) -> NoReturn:  # noqa: ARG002
        """Allow via exit 0, context on stdout."""
        if message is not None:
            print(message, end="")
        sys.exit(0)

    def block(self, message: str) -> NoReturn:
        """Block via exit 2, error on stderr."""
        print(message, end="", file=sys.stderr)
        sys.exit(2)

    def feedback(self, message: str) -> NoReturn:
        """Continue via exit 0, Stop's decision JSON with message as reason.

        Kiro's `Stop` hook only surfaces feedback via this exit-0 JSON
        channel (see kiro.dev/docs/cli/hooks/#stop) - the default
        `Protocol.feedback()` (exit 2 + stderr) is a no-op here since `Stop`
        isn't attached to a tool call and can't be blocked.
        """
        print(json.dumps({"decision": "block", "reason": message}), end="")
        sys.exit(0)

    def research_trace_header(self) -> str:
        """Return the Stop research-trace header for Kiro.

        Unlike Claude Code, Kiro never surfaces this hook's raw output to the
        user - only the model's own reply is shown, appended directly after
        its prior turn text with no separator. So the instruction must tell
        the model to render the trace itself, on its own new line, as a bare
        citation with no narration - otherwise the model tends to explain or
        editorialize about the lookups instead of just listing them. An exact
        format string is spelled out because a looser instruction (e.g. "list
        tool + detail") still let the model invent its own punctuation, such
        as repeating a URL a second time in parentheses.
        """
        return (
            "RESEARCH TRACE: start your reply with a line break, then write ONE "
            "line in exactly this format and nothing else: Sources: <tool> "
            '"<detail>", <tool> "<detail>", ... - substituting each tool/detail '
            "pair from the lookups below, copied verbatim, each detail written "
            "only once. No narration, no commentary, no parentheses, no restating "
            "a detail a second time."
        )
