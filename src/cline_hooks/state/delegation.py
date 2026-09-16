"""Track whether the one-shot inline-work delegation nudge has fired."""

from __future__ import annotations

import json
import logging

from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks")

_STATE_PATH = get_data_dir() / "delegation-state.json"


def _read() -> dict[str, bool]:
    try:
        return dict(json.loads(_STATE_PATH.read_text()))
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def _write(data: dict[str, bool]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(data))


def should_nudge_inline_work(task_id: str) -> bool:
    """Check whether the inline-work delegation nudge should fire, consuming it.

    Fires True the first time it is called for a session; every subsequent
    call for the same session returns False.

    Args:
        task_id: The session or task identifier.

    Returns:
        True only on the first call for this task_id.
    """
    data = _read()
    if data.get(task_id):
        return False
    data[task_id] = True
    _write(data)
    return True


def reset(task_id: str) -> None:
    """Clear the delegation-nudge record for a session.

    Args:
        task_id: The session or task identifier.
    """
    data = _read()
    if task_id in data:
        del data[task_id]
        _write(data)
