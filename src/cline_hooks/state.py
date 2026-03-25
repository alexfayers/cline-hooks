from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import logging
from typing import TYPE_CHECKING, cast

from cline_hooks.paths import get_data_dir

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger("hooks")

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

    def _read(self) -> dict[str, list[dict[str, str]]]:
        """Read state from disk, returning empty dict on missing or corrupt file.

        Returns:
            Mapping of task IDs to lists of block event dicts.
        """
        try:
            return cast("dict[str, list[dict[str, str]]]", json.loads(self._path.read_text()))
        except FileNotFoundError:
            return {}
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to read state file %s; resetting", self._path)
            return {}

    def _write(self, data: dict[str, list[dict[str, str]]]) -> None:
        """Write state to disk."""
        self._path.write_text(json.dumps(data, indent=2))

    def record_block(self, task_id: str, tool_name: str, reason: str) -> None:
        """Store that a tool was blocked for a given task.

        Args:
            task_id: The Cline task identifier.
            tool_name: The tool that was blocked.
            reason: The reason for blocking.
        """
        data = self._read()
        event = TaskBlockEvent(
            tool_name=tool_name,
            reason=reason,
            timestamp=datetime.now(tz=UTC).isoformat(),
        )
        data.setdefault(task_id, []).append(asdict(event))
        self._write(data)

    def get_blocks(self, task_id: str) -> list[TaskBlockEvent]:
        """Retrieve all block events for a task.

        Args:
            task_id: The Cline task identifier.

        Returns:
            List of block events, oldest first.
        """
        data = self._read()
        return [TaskBlockEvent(**e) for e in data.get(task_id, [])]

    def clear_blocks(self, task_id: str) -> None:
        """Clear block history for a completed task.

        Args:
            task_id: The Cline task identifier.
        """
        data = self._read()
        if task_id in data:
            del data[task_id]
            self._write(data)
