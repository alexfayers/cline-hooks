# ruff: noqa: T201
"""Kiro exit-code protocol."""

from __future__ import annotations

import json
import sys
from typing import NoReturn

from cline_hooks.core.protocol import Protocol


class KiroProtocol(Protocol):
    """Kiro exit-code protocol: exit 0 + stdout for allow, exit 2 + stderr for block."""

    def allow(self, message: str | None = None) -> NoReturn:
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
