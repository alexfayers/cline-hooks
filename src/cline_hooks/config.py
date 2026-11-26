"""Shared configuration for the cline-hooks package."""

from __future__ import annotations

import os


def agent_teams_enabled() -> bool:
    """Return whether agent teams are enabled for this session.

    Read from CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS, which the harness gates on
    presence rather than value, so any non-empty value counts as enabled.
    """
    return bool(os.environ.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", ""))


def get_push_block_markers() -> tuple[str, ...]:
    """Return directory/file names marking a workspace where `git push` is blocked.

    Read from CLINE_HOOKS_PUSH_BLOCK_MARKERS (comma-separated), empty by default so
    the guard is opt-in and build-system-agnostic.
    """
    raw = os.environ.get("CLINE_HOOKS_PUSH_BLOCK_MARKERS", "")
    return tuple(marker.strip() for marker in raw.split(",") if marker.strip())


_DEFAULT_MAX_MEMORY_MB = 640


def get_max_memory_mb() -> int:
    """Return the data-segment (private writable memory) cap for one hook process, in megabytes.

    Read from CLINE_HOOKS_MAX_MEMORY_MB, 640 by default or when not a positive integer.
    """
    raw = os.environ.get("CLINE_HOOKS_MAX_MEMORY_MB", "")
    return int(raw) if raw.isdigit() and int(raw) > 0 else _DEFAULT_MAX_MEMORY_MB
