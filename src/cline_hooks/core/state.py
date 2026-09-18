"""Generic per-task JSON state store any plugin can instantiate as a singleton."""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, Any, cast

from cline_hooks.state.jsonfile import discard_key, read_json, updated_json
from cline_hooks.state.paths import get_data_dir

if TYPE_CHECKING:
    from collections.abc import Callable
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
        data: dict[str, dict[str, Any]] = read_json(self._path, {})
        return data if isinstance(data, dict) else {}

    def _parse(self, entry: dict[str, Any]) -> StateT:
        """Build a state instance from a raw entry, falling back to defaults.

        Args:
            entry: The task's raw state field dict.

        Returns:
            The parsed state, or a default-constructed instance on a malformed entry.
        """
        try:
            return self._state_type(**entry) if isinstance(entry, dict) else self._state_type()
        except TypeError:
            return self._state_type()

    def get(self, task_id: str) -> StateT:
        """Return the state entry for a task, or a default instance if none exists.

        Args:
            task_id: The session or task identifier.

        Returns:
            The task's state, or a default-constructed instance on a missing or
            malformed entry.
        """
        return self._parse(self._read_all().get(task_id, {}))

    def update[ResultT](self, task_id: str, mutate: Callable[[StateT], ResultT]) -> ResultT:
        """Mutate a task's state under an exclusive lock, persisting the result.

        Args:
            task_id: The session or task identifier.
            mutate: Called with the task's current state, mutating it in place.

        Returns:
            Whatever the mutation returned.
        """
        with updated_json(self._path, cast("dict[str, dict[str, Any]]", {})) as data:
            state = self._parse(data.get(task_id, {}))
            result = mutate(state)
            data[task_id] = dataclasses.asdict(state)
        return result

    def reset(self, task_id: str) -> None:
        """Clear the state entry for a task.

        Args:
            task_id: The session or task identifier.
        """
        discard_key(self._path, task_id)
