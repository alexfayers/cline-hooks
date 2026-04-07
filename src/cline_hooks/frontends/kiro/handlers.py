"""Kiro-specific hook handlers."""
from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.core.registry import hook_handler

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInput


@hook_handler("Stop")
def handle_stop(_hook: HookInput) -> None:
    """Handle Stop hook events (Kiro only)."""
