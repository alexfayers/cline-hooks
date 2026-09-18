"""Track how many sessions have elapsed since the last retrospective."""

from __future__ import annotations

import logging
from typing import cast

from cline_hooks.state.jsonfile import read_json, updated_json
from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks.state.retrospective")

_STATE_PATH = get_data_dir() / "retrospective-state.json"

_MAX_TRACKED_SESSIONS = 500


def _default() -> dict[str, object]:
    return {"count": 0, "counted_sessions": []}


def record_session(task_id: str) -> int | None:
    """Count a session once, keyed by its identifier.

    Args:
        task_id: The session identifier. A falsy value is ignored.

    Returns:
        The new session count on a fresh increment, or None if the session was
        already counted or the identifier is falsy.
    """
    if not task_id:
        return None
    with updated_json(_STATE_PATH, _default()) as data:
        data.setdefault("count", 0)
        data.setdefault("counted_sessions", [])
        counted = cast("list[str]", data["counted_sessions"])
        if task_id in counted:
            return None
        count = cast("int", data["count"]) + 1
        data["count"] = count
        data["counted_sessions"] = [*counted, task_id][-_MAX_TRACKED_SESSIONS:]
    return count


def get_count() -> int:
    """Return the number of sessions counted since the last reset.

    Returns:
        The current session count.
    """
    data = read_json(_STATE_PATH, _default())
    return cast("int", data["count"])


def reset() -> None:
    """Clear the session count and the per-session guard."""
    with updated_json(_STATE_PATH, _default()) as data:
        data.update(_default())
