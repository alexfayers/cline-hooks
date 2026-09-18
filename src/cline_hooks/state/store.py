from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from cline_hooks.state.jsonfile import discard_key, read_json, updated_json
from cline_hooks.state.paths import get_data_dir

if TYPE_CHECKING:
    from pathlib import Path

_STATE_PATH = get_data_dir() / "hook-state.json"


@dataclass
class TaskBlockEvent:
    """A single block event recorded for a task."""

    tool_name: str
    reason: str
    timestamp: str


class TaskStateStore:
    """Persists per-task block events in a JSON file for cross-hook recall."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path if path is not None else _STATE_PATH

    def record_block(self, task_id: str, tool_name: str, reason: str) -> None:
        """Store that a tool was blocked for a given task.

        Args:
            task_id: The session or task identifier.
            tool_name: The tool that was blocked.
            reason: The reason for blocking.
        """
        event = TaskBlockEvent(
            tool_name=tool_name,
            reason=reason,
            timestamp=datetime.now(tz=UTC).isoformat(),
        )
        with updated_json(self._path, cast("dict[str, list[dict[str, str]]]", {})) as data:
            data.setdefault(task_id, []).append(asdict(event))

    def get_blocks(self, task_id: str) -> list[TaskBlockEvent]:
        """Retrieve all block events for a task.

        Args:
            task_id: The session or task identifier.

        Returns:
            List of block events, oldest first.
        """
        data: dict[str, list[dict[str, str]]] = read_json(self._path, {})
        return [TaskBlockEvent(**e) for e in data.get(task_id, [])]

    def clear_blocks(self, task_id: str) -> None:
        """Clear block history for a completed task.

        Args:
            task_id: The session or task identifier.
        """
        discard_key(self._path, task_id)
