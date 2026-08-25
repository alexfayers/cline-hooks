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


def is_frustration_detector_disabled() -> bool:
    """Return True when the correction/frustration detector is disabled.

    Read from CLINE_HOOKS_DISABLE_FRUSTRATION_DETECTOR. Disabled when set to
    ``"1"``, ``"true"``, or ``"yes"`` (case-insensitive); enabled by default.
    """
    return os.environ.get("CLINE_HOOKS_DISABLE_FRUSTRATION_DETECTOR", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
