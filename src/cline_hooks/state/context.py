"""Track context-token banding and degradation-boundary crossings per session."""

from __future__ import annotations

import json
import logging

from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks")

_STATE_PATH = get_data_dir() / "context-state.json"

_BAND_SIZE = 10_000

CONTEXT_REDUCED_THRESHOLD = 200_000
CONTEXT_DEGRADED_THRESHOLD = 400_000
_BOUNDARIES: tuple[int, ...] = (CONTEXT_REDUCED_THRESHOLD, CONTEXT_DEGRADED_THRESHOLD)


def _read() -> dict[str, dict[str, int]]:
    try:
        raw = json.loads(_STATE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: ({"band": v} if isinstance(v, int) else v) for k, v in raw.items()}


def _write(data: dict[str, dict[str, int]]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(data))


def _band_for(token_count: int) -> int:
    """Return the band index for a token count.

    Bands are fixed-width slices of BAND_SIZE tokens counted from zero, so band 0
    covers [0, BAND_SIZE), band 1 the next slice, and so on.

    Args:
        token_count: The current context token count.

    Returns:
        The zero-based band index.
    """
    return token_count // _BAND_SIZE


def should_nudge_context(task_id: str, token_count: int) -> bool:
    """Check whether the current token count crosses into a new context band.

    Fires once per band. The highest band already nudged for the session is
    persisted, so a nudge fires only when the count crosses into a band not yet
    nudged for this task.

    Args:
        task_id: The session or task identifier.
        token_count: The current context token count.

    Returns:
        True if the token count has entered a band not yet nudged this session.
    """
    band = _band_for(token_count)
    data = _read()
    entry = data.get(task_id, {})
    last_band = entry.get("band")
    if last_band is not None and band <= last_band:
        return False
    entry["band"] = band
    data[task_id] = entry
    _write(data)
    return True


def crossed_boundary(task_id: str, token_count: int) -> int | None:
    """Return the degradation boundary newly crossed by this token count, or None.

    Fires once per boundary per session: the first call whose token count reaches
    a boundary (CONTEXT_REDUCED_THRESHOLD or CONTEXT_DEGRADED_THRESHOLD) not yet
    announced for this task returns that boundary; later calls at or above the
    same boundary return None.

    Args:
        task_id: The session or task identifier.
        token_count: The current context token count.

    Returns:
        The boundary just crossed, or None if no new boundary was reached.
    """
    data = _read()
    entry = data.get(task_id, {})
    last_boundary = entry.get("boundary", 0)
    newly_crossed = [b for b in _BOUNDARIES if token_count >= b > last_boundary]
    if not newly_crossed:
        return None
    boundary = max(newly_crossed)
    entry["boundary"] = boundary
    data[task_id] = entry
    _write(data)
    return boundary


def reset(task_id: str) -> None:
    """Clear the nudged-band and boundary record for a session.

    Args:
        task_id: The session or task identifier.
    """
    data = _read()
    if task_id in data:
        del data[task_id]
        _write(data)
