"""Track how many sessions have elapsed since the last retrospective."""

from __future__ import annotations

import json
import logging
from typing import cast

from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks")

_STATE_PATH = get_data_dir() / "retrospective-state.json"

_MAX_TRACKED_SESSIONS = 500


def _read() -> dict[str, object]:
    try:
        data = cast("dict[str, object]", json.loads(_STATE_PATH.read_text()))
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return {"count": 0, "counted_sessions": []}
    data.setdefault("count", 0)
    data.setdefault("counted_sessions", [])
    return data


def _write(count: int, counted_sessions: list[str]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps({"count": count, "counted_sessions": counted_sessions}))


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
    data = _read()
    counted = cast("list[str]", data["counted_sessions"])
    if task_id in counted:
        return None
    count = cast("int", data["count"]) + 1
    counted = [*counted, task_id][-_MAX_TRACKED_SESSIONS:]
    _write(count, counted)
    return count


def get_count() -> int:
    """Return the number of sessions counted since the last reset.

    Returns:
        The current session count.
    """
    return cast("int", _read()["count"])


def reset() -> None:
    """Clear the session count and the per-session guard."""
    _write(0, [])
