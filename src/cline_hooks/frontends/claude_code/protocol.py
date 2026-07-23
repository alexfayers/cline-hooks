# ruff: noqa: T201
"""Claude Code exit-code protocol."""

from __future__ import annotations

import json
import sys
from typing import NoReturn

from cline_hooks.frontends.kiro.protocol import KiroProtocol


class ClaudeCodeProtocol(KiroProtocol):
    """Claude Code exit-code protocol.

    Same allow/block as Kiro, but Stop feedback uses
    hookSpecificOutput.additionalContext (exit 0) instead of exit 2,
    avoiding the 'Stop hook error:' UI framing.
    """

    def feedback(self, message: str) -> NoReturn:
        """Continue via exit 0, non-error context in hookSpecificOutput."""
        print(
            json.dumps(
                {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": message}},
            ),
            end="",
        )
        sys.exit(0)
