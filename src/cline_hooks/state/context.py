"""Track context-token banding per session to nudge fresh-session starts."""

from __future__ import annotations

import json
import logging

from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks")

_STATE_PATH = get_data_dir() / "context-state.json"

_CONTEXT_THRESHOLD = 200_000
_BAND_SIZE = 50_000


def _read() -> dict[str, int]:
    try:
        return dict(json.loads(_STATE_PATH.read_text()))
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def _write(data: dict[str, int]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(data))


def _band_for(token_count: int) -> int | None:
    """Return the band index for a token count, or None when below threshold.

    Band 0 covers [threshold, threshold + band_size), band 1 the next slice, and so on.

    Args:
        token_count: The current context token count.

    Returns:
        The zero-based band index, or None if below the threshold.
    """
    if token_count < _CONTEXT_THRESHOLD:
        return None
    return (token_count - _CONTEXT_THRESHOLD) // _BAND_SIZE


def should_nudge_context(task_id: str, token_count: int) -> bool:
    """Check whether the current token count should trigger a context nudge.

    Fires once per band above the threshold. The highest band already nudged for
    the session is persisted, so a nudge fires only when the count crosses into a
    band not yet nudged for this task.

    Args:
        task_id: The session or task identifier.
        token_count: The current context token count.

    Returns:
        True if a context nudge should be shown for this band.
    """
    band = _band_for(token_count)
    if band is None:
        return False
    data = _read()
    last = data.get(task_id)
    if last is not None and band <= last:
        return False
    data[task_id] = band
    _write(data)
    return True


def reset(task_id: str) -> None:
    """Clear the nudged-band record for a session.

    Args:
        task_id: The session or task identifier.
    """
    data = _read()
    if task_id in data:
        del data[task_id]
        _write(data)
