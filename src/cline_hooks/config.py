"""Shared configuration for the cline-hooks package."""

from __future__ import annotations

import os


def get_push_block_markers() -> tuple[str, ...]:
    """Return directory/file names marking a workspace where `git push` is blocked.

    Read from CLINE_HOOKS_PUSH_BLOCK_MARKERS (comma-separated), empty by default so
    the guard is opt-in and build-system-agnostic.
    """
    raw = os.environ.get("CLINE_HOOKS_PUSH_BLOCK_MARKERS", "")
    return tuple(marker.strip() for marker in raw.split(",") if marker.strip())
