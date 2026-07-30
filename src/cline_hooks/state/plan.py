"""Track whether a plan-mode exit occurred, to nudge a fresh-session handoff."""

from __future__ import annotations

import json
import logging

from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks")

_STATE_PATH = get_data_dir() / "plan-state.json"

_PLAN_EXIT_TOOLS: frozenset[str] = frozenset({"ExitPlanMode"})


def _read() -> dict[str, bool]:
    try:
        return dict(json.loads(_STATE_PATH.read_text()))
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def _write(data: dict[str, bool]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(data))


def is_plan_exit_tool(tool_name: str) -> bool:
    """Check whether a tool name marks the end of plan mode.

    Args:
        tool_name: The tool name as reported by the frontend.

    Returns:
        True if the tool signals a plan-mode exit.
    """
    return tool_name in _PLAN_EXIT_TOOLS


def record_plan_exit(task_id: str) -> None:
    """Record that a plan-mode exit occurred this session.

    Arms a one-shot handoff nudge to be shown on the next user prompt.

    Args:
        task_id: The session or task identifier.
    """
    data = _read()
    data[task_id] = True
    _write(data)


def consume_plan_nudge(task_id: str) -> bool:
    """Return whether a pending plan-handoff nudge should fire, consuming it.

    Fires True at most once per recorded plan exit; subsequent calls return
    False until another plan exit is recorded.

    Args:
        task_id: The session or task identifier.

    Returns:
        True if a plan-handoff nudge is pending for this session.
    """
    data = _read()
    if not data.get(task_id):
        return False
    data[task_id] = False
    _write(data)
    return True


def reset(task_id: str) -> None:
    """Clear the plan-exit record for a session.

    Args:
        task_id: The session or task identifier.
    """
    data = _read()
    if task_id in data:
        del data[task_id]
        _write(data)
