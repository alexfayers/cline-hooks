# ruff: noqa: T201
"""Cline JSON stdout protocol."""

from __future__ import annotations

import json
import sys
from typing import NoReturn

from cline_hooks.core.protocol import Protocol


class ClineProtocol(Protocol):
    """Cline JSON stdout protocol."""

    def allow(self, message: str | None = None, *, system_message: str | None = None) -> NoReturn:  # noqa: ARG002
        """Allow via JSON stdout."""
        res: dict[str, object] = {"cancel": False}
        if message is not None:
            res["contextModification"] = message
        print(json.dumps(res), end="")
        sys.exit(0)

    def block(self, message: str) -> NoReturn:
        """Block via JSON stdout."""
        res: dict[str, object] = {"cancel": True, "errorMessage": message}
        print(json.dumps(res), end="")
        sys.exit(0)
