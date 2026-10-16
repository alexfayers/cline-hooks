"""Track which subagents are live or finished during a session."""

from __future__ import annotations

import logging

from cline_hooks.state.jsonfile import discard_prefix, read_json, updated_json
from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks.state.finished")

_STATE_PATH = get_data_dir() / "finished-agents.json"


def mark_finished(state_key: str) -> None:
    """Record that a subagent has finished.

    Args:
        state_key: The subagent's per-agent state key (`<task_id>:<agent_id>`).
    """
    empty: dict[str, bool] = {}
    with updated_json(_STATE_PATH, empty) as data:
        data[state_key] = True


def mark_started(state_key: str) -> None:
    """Record that a subagent is live, clearing any finished flag from an earlier run.

    Args:
        state_key: The subagent's per-agent state key (`<task_id>:<agent_id>`).
    """
    empty: dict[str, bool] = {}
    with updated_json(_STATE_PATH, empty) as data:
        data[state_key] = False


def finished_keys(task_id: str) -> set[str]:
    """Return the state keys of a session's finished subagents.

    Args:
        task_id: The session or task identifier.

    Returns:
        Every finished per-agent state key nested under the session.
    """
    return _keys_nested_under(task_id, finished=True)


def live_keys(task_id: str) -> set[str]:
    """Return the state keys of a session's subagents that have started and not stopped.

    Args:
        task_id: The session or task identifier.

    Returns:
        Every live per-agent state key nested under the session.
    """
    return _keys_nested_under(task_id, finished=False)


def _keys_nested_under(task_id: str, *, finished: bool) -> set[str]:
    data: dict[str, bool] = read_json(_STATE_PATH, {})
    prefix = f"{task_id}:"
    return {key for key, is_finished in data.items() if key.startswith(prefix) and is_finished is finished}


def reset(task_id: str) -> None:
    """Clear every finished-subagent record under a session.

    Args:
        task_id: The session or task identifier.
    """
    discard_prefix(_STATE_PATH, f"{task_id}:")
