"""Generic per-task JSON state store any plugin can instantiate as a singleton."""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import TYPE_CHECKING, Any

from cline_hooks.state.paths import get_data_dir

if TYPE_CHECKING:
    from pathlib import Path

    from _typeshed import DataclassInstance

logger = logging.getLogger("hooks.state")


class PluginStateStore[StateT: "DataclassInstance"]:
    """Reads/writes one plugin's per-task-keyed JSON state file."""

    def __init__(self, filename: str, state_type: type[StateT], path: Path | None = None) -> None:
        """Configure the store's backing file and per-task dataclass shape.

        Args:
            filename: The state file's name under the platform data directory.
            state_type: The dataclass type used for each task's state entry.
            path: An explicit backing file path, overriding the data-dir default.
        """
        self._path = path if path is not None else get_data_dir() / filename
        self._state_type = state_type

    def _read_all(self) -> dict[str, dict[str, Any]]:
        """Read the whole state file, returning empty on a missing or corrupt file.

        Returns:
            Mapping of task IDs to their raw state field dicts.
        """
        try:
            raw = json.loads(self._path.read_text())
        except (
            FileNotFoundError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            OSError,
        ):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write_all(self, data: dict[str, dict[str, Any]]) -> None:
        """Atomically write the whole state file via a tmp-file-then-replace.

        Args:
            data: Mapping of task IDs to their raw state field dicts.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(self._path)

    def get(self, task_id: str) -> StateT:
        """Return the state entry for a task, or a default instance if none exists.

        Args:
            task_id: The session or task identifier.

        Returns:
            The task's state, or a default-constructed instance on a missing or
            malformed entry.
        """
        entry = self._read_all().get(task_id, {})
        try:
            return self._state_type(**entry) if isinstance(entry, dict) else self._state_type()
        except TypeError:
            return self._state_type()

    def set(self, task_id: str, state: StateT) -> None:
        """Store the state entry for a task.

        Args:
            task_id: The session or task identifier.
            state: The state to persist.
        """
        data = self._read_all()
        data[task_id] = dataclasses.asdict(state)
        self._write_all(data)

    def reset(self, task_id: str) -> None:
        """Clear the state entry for a task.

        Args:
            task_id: The session or task identifier.
        """
        data = self._read_all()
        if data.pop(task_id, None) is not None:
            self._write_all(data)
