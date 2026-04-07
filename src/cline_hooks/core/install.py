"""Shared install utilities."""
from __future__ import annotations

from pathlib import Path
import sys


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
