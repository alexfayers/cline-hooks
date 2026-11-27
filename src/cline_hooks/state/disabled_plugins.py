"""Persist which plugins the user disabled, with an optional reason and the time."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from cline_hooks.state.jsonfile import read_json, updated_json
from cline_hooks.state.paths import get_data_dir

_STATE_PATH = get_data_dir() / "disabled_plugins.json"


class DisabledPlugin(TypedDict):
    reason: str | None
    at: str


def disable(name: str, reason: str | None = None) -> None:
    """Disable a plugin for every session until it is enabled again.

    Args:
        name: The plugin's class name.
        reason: Why the plugin was disabled, kept for auditing.
    """
    with updated_json(_STATE_PATH, dict[str, DisabledPlugin]()) as data:
        _drop_malformed(data)
        data[name] = {"reason": reason, "at": datetime.now(UTC).isoformat(timespec="seconds")}


def enable(name: str) -> None:
    """Enable a disabled plugin.

    Args:
        name: The plugin's class name.
    """
    with updated_json(_STATE_PATH, dict[str, DisabledPlugin]()) as data:
        _drop_malformed(data)
        data.pop(name, None)


def _drop_malformed(data: dict[str, DisabledPlugin]) -> None:
    """Remove every entry of the wrong shape, in place."""
    for name in [name for name, entry in data.items() if not _is_entry(entry)]:
        del data[name]


def _is_entry(entry: object) -> bool:
    return isinstance(entry, dict) and isinstance(entry.get("at"), str) and isinstance(entry.get("reason"), str | None)


def disabled_plugins() -> dict[str, DisabledPlugin]:
    """Return the disabled plugins, keyed by class name.

    Returns:
        Each disabled plugin's reason and the time it was disabled, leaving out
        any entry of the wrong shape, so a damaged file leaves plugins enabled.
    """
    data = read_json(_STATE_PATH, dict[str, DisabledPlugin]())
    _drop_malformed(data)
    return data
