"""Track the last workspace roots seen per session to detect mid-session moves."""

from __future__ import annotations

import json
import logging

from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks")

_STATE_PATH = get_data_dir() / "workspace-state.json"


def _read() -> dict[str, list[str]]:
    try:
        return dict(json.loads(_STATE_PATH.read_text()))
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def _write(data: dict[str, list[str]]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(data))


def record_workspace(task_id: str, workspace_roots: list[str]) -> None:
    """Record the workspace roots the agent has already been told about.

    Args:
        task_id: The session or task identifier.
        workspace_roots: The workspace root paths for this event.
    """
    if not workspace_roots:
        return
    data = _read()
    data[task_id] = list(workspace_roots)
    _write(data)


def should_note_workspace_change(task_id: str, workspace_roots: list[str]) -> bool:
    """Check whether the workspace roots differ from the last recorded ones.

    First sighting for a session records silently - task start/resume has
    already delivered context for those roots. The store is "last seen", not
    "ever seen": returning to a previously-visited directory fires again,
    since the note is guidance about where the agent is now.

    Args:
        task_id: The session or task identifier.
        workspace_roots: The workspace root paths for this event.

    Returns:
        True if the roots changed from the last recorded value for this session.
    """
    if not workspace_roots:
        return False
    data = _read()
    previous = data.get(task_id)
    if previous == list(workspace_roots):
        return False
    data[task_id] = list(workspace_roots)
    _write(data)
    return previous is not None


def reset(task_id: str) -> None:
    """Clear the recorded workspace roots for a session.

    Args:
        task_id: The session or task identifier.
    """
    data = _read()
    if task_id in data:
        del data[task_id]
        _write(data)
