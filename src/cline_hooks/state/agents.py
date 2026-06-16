"""Track whether subagent-spawning tools were used during a session."""

from __future__ import annotations

import json
import logging

from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks")

_STATE_PATH = get_data_dir() / "agents-state.json"

_AGENT_TOOLS: frozenset[str] = frozenset({
    "Agent",
    "Workflow",
    "new_task",
    "subagent",
})


def _read() -> dict[str, list[str]]:
    try:
        return dict(json.loads(_STATE_PATH.read_text()))
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def _write(data: dict[str, list[str]]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(data))


def is_agent_tool(tool_name: str) -> bool:
    """Check whether a tool name spawns a subagent.

    Args:
        tool_name: The tool name as reported by the frontend.

    Returns:
        True if the tool fans work out to a subagent.
    """
    return tool_name in _AGENT_TOOLS


def record_agent_use(task_id: str, tool_name: str) -> None:
    """Record that a subagent-spawning tool was called for a session.

    Every invocation is recorded so the per-session count reflects fan-out volume,
    not just whether a subagent was ever used.

    Args:
        task_id: The session or task identifier.
        tool_name: The agent tool that was called.
    """
    data = _read()
    data[task_id] = [*data.get(task_id, []), tool_name]
    _write(data)


def has_agent_use(task_id: str) -> bool:
    """Check whether any subagent-spawning tool was called for a session.

    Args:
        task_id: The session or task identifier.

    Returns:
        True if at least one agent tool was called.
    """
    return bool(_read().get(task_id))


def agent_use_count(task_id: str) -> int:
    """Return how many subagent-spawning tool calls were recorded for a session.

    Args:
        task_id: The session or task identifier.

    Returns:
        The total number of agent tool invocations recorded.
    """
    return len(_read().get(task_id, []))


def reset(task_id: str) -> None:
    """Clear recorded agent use for a session.

    Args:
        task_id: The session or task identifier.
    """
    data = _read()
    if task_id in data:
        del data[task_id]
        _write(data)
