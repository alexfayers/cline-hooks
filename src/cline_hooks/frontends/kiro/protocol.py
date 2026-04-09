# ruff: noqa: T201
"""Kiro exit-code protocol."""

from __future__ import annotations

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
