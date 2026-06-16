"""Track user prompt turn count per session for scope-creep detection."""

from __future__ import annotations

import json
import logging

from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks")

_STATE_PATH = get_data_dir() / "turns-state.json"

_SCOPE_CHECK_THRESHOLD = 80
_REMINDER_INTERVAL = 40
_AGENT_NUDGE_THRESHOLD = 50


def _read() -> dict[str, int]:
    try:
        return dict(json.loads(_STATE_PATH.read_text()))
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def _write(data: dict[str, int]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(data))


def increment(task_id: str) -> int:
    """Increment and return the turn count for a session.

    Args:
        task_id: The session or task identifier.

    Returns:
        The new turn count after incrementing.
    """
    data = _read()
    count = data.get(task_id, 0) + 1
    data[task_id] = count
    _write(data)
    return count


def should_remind(turn_count: int) -> bool:
    """Check whether the current turn count should trigger a scope reminder.

    Triggers at the threshold, then every REMINDER_INTERVAL turns after.

    Args:
        turn_count: The current turn count.

    Returns:
        True if a scope-check reminder should be shown.
    """
    if turn_count < _SCOPE_CHECK_THRESHOLD:
        return False
    return (turn_count - _SCOPE_CHECK_THRESHOLD) % _REMINDER_INTERVAL == 0


def should_nudge_agents(turn_count: int, agent_count: int) -> bool:
    """Check whether to nudge for more subagent fan-out, based on usage rate.

    Evaluated only on turn-count checkpoints (every AGENT_NUDGE_THRESHOLD turns).
    The target is roughly one subagent per checkpoint; the nudge fires whenever the
    recorded agent count has fallen behind that target as the session grows. This
    re-fires in long sessions that used a few subagents early but then ran on
    sequentially, not just in sessions that never used one.

    Args:
        turn_count: The current turn count.
        agent_count: The number of subagent invocations recorded this session.

    Returns:
        True if an agent fan-out nudge should be shown.
    """
    if turn_count < _AGENT_NUDGE_THRESHOLD or turn_count % _AGENT_NUDGE_THRESHOLD != 0:
        return False
    return agent_count < turn_count // _AGENT_NUDGE_THRESHOLD


def reset(task_id: str) -> None:
    """Clear the turn count for a session.

    Args:
        task_id: The session or task identifier.
    """
    data = _read()
    if task_id in data:
        del data[task_id]
        _write(data)
