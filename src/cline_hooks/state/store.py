from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from cline_hooks.state.jsonfile import discard_key, discard_prefix, read_json, updated_json
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

    def clear_blocks(self, task_id: str, *, discard_children: bool = True) -> None:
        """Clear block history for a task.

        Args:
            task_id: The session or task identifier.
            discard_children: Also clear every per-agent history nested under
                this task id. Set False for a per-turn reset that must not
                disturb another agent's still-running block history.
        """
        discard_key(self._path, task_id)
        if discard_children:
            discard_prefix(self._path, f"{task_id}:")
