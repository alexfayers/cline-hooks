from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("hooks")

_MEMORY_BLOCK_THRESHOLD = 10
_STATE_PATH = Path(__file__).parent.parent.parent / ".memory-tracker-state.json"


def _read() -> dict[str, int]:
    try:
        return dict(json.loads(_STATE_PATH.read_text()))
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def _write(data: dict[str, int]) -> None:
    _STATE_PATH.write_text(json.dumps(data))


def increment(task_id: str) -> int:
    """Increment the tool-call counter for a task and return the new value.

    Args:
        task_id: The Cline task identifier.

    Returns:
        The updated counter value.
    """
    data = _read()
    data[task_id] = data.get(task_id, 0) + 1
    _write(data)
    return data[task_id]


def reset(task_id: str) -> None:
    """Reset the tool-call counter to zero after a memory write.

    Args:
        task_id: The Cline task identifier.
    """
    data = _read()
    data[task_id] = 0
    _write(data)


def should_block(task_id: str, threshold: int = _MEMORY_BLOCK_THRESHOLD) -> bool:
    """Return True if the counter has reached the blocking threshold.

    Args:
        task_id: The Cline task identifier.
        threshold: Number of tool calls without a memory write before blocking.

    Returns:
        True if the task should be blocked.
    """
    return _read().get(task_id, 0) >= threshold


def clear(task_id: str) -> None:
    """Remove the counter entry for a completed task.

    Args:
        task_id: The Cline task identifier.
    """
    data = _read()
    if task_id in data:
        del data[task_id]
        _write(data)
