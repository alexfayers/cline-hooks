"""Track whether subagent-spawning tools were used during a session."""

from __future__ import annotations

import logging

from cline_hooks.core.vocabulary import AGENT_SPAWN_TOOLS
from cline_hooks.state.jsonfile import discard_key, read_json, updated_json
from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks.state.agents")

_STATE_PATH = get_data_dir() / "agents-state.json"


def is_agent_tool(tool_name: str) -> bool:
    """Check whether a tool name spawns a subagent.

    Args:
        tool_name: The tool name as reported by the frontend.

    Returns:
        True if the tool fans work out to a subagent.
    """
    return tool_name in AGENT_SPAWN_TOOLS


def record_agent_use(task_id: str, tool_name: str) -> None:
    """Record that a subagent-spawning tool was called for a session.

    Every invocation is recorded so the per-session count reflects fan-out volume,
    not just whether a subagent was ever used.

    Args:
        task_id: The session or task identifier.
        tool_name: The agent tool that was called.
    """
    empty: dict[str, list[str]] = {}
    with updated_json(_STATE_PATH, empty) as data:
        data[task_id] = [*data.get(task_id, []), tool_name]


def has_agent_use(task_id: str) -> bool:
    """Check whether any subagent-spawning tool was called for a session.

    Args:
        task_id: The session or task identifier.

    Returns:
        True if at least one agent tool was called.
    """
    data: dict[str, list[str]] = read_json(_STATE_PATH, {})
    return bool(data.get(task_id))


def agent_use_count(task_id: str) -> int:
    """Return how many subagent-spawning tool calls were recorded for a session.

    Args:
        task_id: The session or task identifier.

    Returns:
        The total number of agent tool invocations recorded.
    """
    data: dict[str, list[str]] = read_json(_STATE_PATH, {})
    return len(data.get(task_id, []))


def reset(task_id: str) -> None:
    """Clear recorded agent use for a session.

    Args:
        task_id: The session or task identifier.
    """
    discard_key(_STATE_PATH, task_id)
