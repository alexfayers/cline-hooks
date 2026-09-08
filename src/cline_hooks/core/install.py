"""Shared install utilities."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_hooks.core.protocol import HookRegistration, Protocol


def build_hook_registrations(protocol_cls: type[Protocol]) -> list[HookRegistration]:
    """Build the ordered list of hook registrations for a frontend's install step.

    Replaces each frontend's own hand-maintained hook list
    (`_KIRO_HOOKS`, `_CLAUDE_CODE_HOOKS`, `_HOOKS`, `_COPILOT_HOOKS`) with a
    single source of truth: the protocol's own `supported_hooks` table.

    Args:
        protocol_cls: The frontend Protocol class to install hooks for.

    Returns:
        Each `HookRegistration` from `protocol_cls.supported_hooks`, in
        declaration order.
    """
    return list(protocol_cls.supported_hooks.values())


def resolve_binary() -> Path:
    """Resolve the path to the cline-hook binary.

    Returns:
        Path to the binary, preferring existing files.
    """
    scripts_dir = Path(sys.executable).parent
    candidates = (
        scripts_dir / "cline-hook",
        scripts_dir / "cline-hook.exe",
        scripts_dir / "cline-hook.cmd",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]
