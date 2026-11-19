"""Shared configuration for the cline-hooks package."""

from __future__ import annotations

import os

from cline_hooks.state.jsonfile import read_json, updated_json
from cline_hooks.state.paths import get_data_dir

CONFIG_PATH = get_data_dir() / "config.json"
MAX_IN_FLIGHT_REVIEWS_KEY = "max_in_flight_reviews"
_DEFAULT_MAX_IN_FLIGHT_REVIEWS = 5


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


def get_max_in_flight_reviews() -> int:
    """Return how many created reviews may be open at once before a new one is blocked.

    Read from `max_in_flight_reviews` in the data directory's `config.json` on each call.
    Defaults to 5 when unset or not an integer.
    """
    config = read_json(CONFIG_PATH, dict[str, object]())
    value = config.get(MAX_IN_FLIGHT_REVIEWS_KEY) if isinstance(config, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else _DEFAULT_MAX_IN_FLIGHT_REVIEWS


def set_max_in_flight_reviews(limit: int) -> None:
    """Write `max_in_flight_reviews` to the data directory's `config.json`, keeping its other keys."""
    with updated_json(CONFIG_PATH, dict[str, object]()) as config:
        config[MAX_IN_FLIGHT_REVIEWS_KEY] = limit
