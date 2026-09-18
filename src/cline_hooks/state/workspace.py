"""Track the last workspace roots seen per session to detect mid-session moves."""

from __future__ import annotations

import logging
from typing import cast

from cline_hooks.state.jsonfile import discard_key, updated_json
from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks.state.workspace")

_STATE_PATH = get_data_dir() / "workspace-state.json"


def record_workspace(task_id: str, workspace_roots: list[str]) -> None:
    """Record the workspace roots the agent has already been told about.

    Args:
        task_id: The session or task identifier.
        workspace_roots: The workspace root paths for this event.
    """
    if not workspace_roots:
        return
    with updated_json(_STATE_PATH, cast("dict[str, list[str]]", {})) as data:
        data[task_id] = list(workspace_roots)


def should_note_workspace_change(task_id: str, workspace_roots: list[str]) -> bool:
    """Check whether the workspace roots differ from the last recorded ones.

    A session's first sighting records silently, since task start/resume has
    already delivered that context. The store is "last seen", not "ever seen",
    so returning to a previous directory fires again.

    Args:
        task_id: The session or task identifier.
        workspace_roots: The workspace root paths for this event.

    Returns:
        True if the roots changed from the last recorded value for this session.
    """
    if not workspace_roots:
        return False
    with updated_json(_STATE_PATH, cast("dict[str, list[str]]", {})) as data:
        previous = data.get(task_id)
        if previous == list(workspace_roots):
            return False
        data[task_id] = list(workspace_roots)
    return previous is not None


def reset(task_id: str) -> None:
    """Clear the recorded workspace roots for a session.

    Args:
        task_id: The session or task identifier.
    """
    discard_key(_STATE_PATH, task_id)
