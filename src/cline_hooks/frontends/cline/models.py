# ruff: noqa: N815
"""Cline-specific HookInput subclass."""
from __future__ import annotations

from dataclasses import dataclass

from cline_hooks.models import HookInput


@dataclass
class ClineHookInput(HookInput):
    """HookInput with Cline-specific metadata fields."""

    clineVersion: str = ""
    timestamp: str = ""
    userId: str = ""
    model: str | None = None
