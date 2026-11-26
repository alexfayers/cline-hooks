"""Generic per-task JSON state store any plugin can instantiate as a singleton."""

from __future__ import annotations

import dataclasses
import hashlib
import logging
from typing import TYPE_CHECKING, Any, cast

from cline_hooks.state.finished import finished_keys
from cline_hooks.state.jsonfile import discard_key, discard_prefix, read_json, updated_json
from cline_hooks.state.paths import get_data_dir

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from _typeshed import DataclassInstance

logger = logging.getLogger("hooks.state")

_ANCHORS_DIR = get_data_dir() / "context-anchors"
_LAYERS = "_layers"


@dataclasses.dataclass(frozen=True)
class _HookContext:
    """The agent context the current hook call runs in."""

    state_key: str = ""
    anchor_id: str | None = None
    live_anchors: frozenset[str] | None = None


_context = _HookContext()


def set_hook_context(state_key: str, anchor_id: str | None, context_anchors: list[str] | None) -> None:
    """Set the agent context that state reads and writes for `state_key` apply to.

    Args:
        state_key: The per-agent state key of the current call.
        anchor_id: The id of the point in the agent's context where this call fires.
        context_anchors: The ids still in the agent's context, or None to reuse the
            last list sent for `state_key` where it holds `anchor_id`.
    """
    global _context  # ruff: ignore[global-statement]
    path = _ANCHORS_DIR / f"{hashlib.sha256(state_key.encode()).hexdigest()[:16]}.json"
    if context_anchors is None:
        cached: list[str] = read_json(path, [])
        context_anchors = cached if isinstance(cached, list) and anchor_id in cached else None
    else:
        with updated_json(path, cast("list[str]", [])) as data:
            data[:] = context_anchors
    live = frozenset(context_anchors) if context_anchors is not None else None
    _context = _HookContext(state_key, anchor_id, live)


def _live_anchors(key: str) -> frozenset[str] | None:
    """Return the anchors still in context for `key`, or None when the current call has none for it."""
    return _context.live_anchors if key == _context.state_key else None


def _live_layers(key: str, entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Return an entry's state layers still in the current context, oldest first.

    Args:
        key: The entry's state key.
        entry: The raw entry: a plain state dict, or `_layers` of anchored states.

    Returns:
        Every layer when the call has no anchors for `key`, else the layers with
        no anchor or an anchor still in context.
    """
    layers = entry.get(_LAYERS) if isinstance(entry, dict) else None
    if not isinstance(layers, list):
        layers = [{"anchor": None, "state": entry}] if entry else []
    live = _live_anchors(key)
    if live is None:
        return layers
    return [layer for layer in layers if layer.get("anchor") is None or layer.get("anchor") in live]


def _visible(key: str, entry: dict[str, Any]) -> dict[str, Any]:
    """Return the raw state of an entry as the current context sees it.

    Returns:
        The state of the newest live layer, or empty when none is live.
    """
    layers = _live_layers(key, entry)
    return layers[-1]["state"] if layers else {}


def _written(key: str, entry: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """Return the raw entry to store after the current call changed its state.

    Returns:
        The plain state for a plain entry the call has no anchors for, else the
        live layers plus the new state anchored to the current call, or for
        another agent's key, to that key's newest anchor.
    """
    layered = isinstance(entry, dict) and isinstance(entry.get(_LAYERS), list)
    if not layered and _live_anchors(key) is None:
        return state
    layers = _live_layers(key, entry)
    if layers and layers[-1]["state"] == state:
        return {_LAYERS: layers}
    newest = layers[-1].get("anchor") if layers else None
    anchor = _context.anchor_id if key == _context.state_key else newest
    if layers and newest == anchor:
        layers.pop()
    return {_LAYERS: [*layers, {"anchor": anchor, "state": state}]}


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
            Mapping of task IDs to their raw state field dicts, as the current context sees them.
        """
        data: dict[str, dict[str, Any]] = read_json(self._path, {})
        return {key: _visible(key, entry) for key, entry in data.items()} if isinstance(data, dict) else {}

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
            entry = data.get(task_id, {})
            state = self._parse(_visible(task_id, entry))
            result = mutate(state)
            data[task_id] = _written(task_id, entry, dataclasses.asdict(state))
        return result

    def update_all(self, mutate: Callable[[StateT], object]) -> None:
        """Mutate every task's state under an exclusive lock, persisting the result.

        Args:
            mutate: Called with each task's current state, mutating it in place.
        """
        with updated_json(self._path, cast("dict[str, dict[str, Any]]", {})) as data:
            for task_id, entry in data.items():
                state = self._parse(_visible(task_id, entry))
                mutate(state)
                data[task_id] = _written(task_id, entry, dataclasses.asdict(state))

    def reset(self, task_id: str) -> None:
        """Clear the state entry for a task and every per-agent entry nested under it.

        Args:
            task_id: The session or task identifier.
        """
        discard_key(self._path, task_id)
        discard_prefix(self._path, f"{task_id}:")

    def drain(self, task_id: str, *, finished_only: bool = False) -> list[StateT]:
        """Remove and return a task's state entry and the per-agent entries nested under it.

        The presence check runs before the lock, so draining an absent task creates no
        file and takes no lock. The task's own entry is always drained; with
        `finished_only`, per-agent entries of unfinished subagents stay in the file.

        Args:
            task_id: The session or task identifier.
            finished_only: Drain only the per-agent entries of finished subagents.

        Returns:
            The task's own state first, then its per-agent states in file order.
        """
        prefix = f"{task_id}:"
        if not any(key == task_id or key.startswith(prefix) for key in self._read_all()):
            return []
        finished = finished_keys(task_id) if finished_only else None
        with updated_json(self._path, cast("dict[str, dict[str, Any]]", {})) as data:
            keys = [task_id] if task_id in data else []
            keys += [key for key in data if key.startswith(prefix) and (finished is None or key in finished)]
            return [self._parse(_visible(key, data.pop(key))) for key in keys]
