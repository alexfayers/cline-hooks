"""Track whether subagent-spawning tools were used during a session."""

from __future__ import annotations

import logging

from cline_hooks.core.state import NameStore
from cline_hooks.core.vocabulary import AGENT_SPAWN_TOOLS

logger = logging.getLogger("hooks.state.agents")

_store = NameStore("agents-state.json")
_START_PREFIX = "start:"


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
    _store.add(task_id, tool_name, repeat=True)


def record_agent_start(task_id: str, agent_id: str) -> None:
    """Record a subagent's start once per agent, so a resume or teammate message does not count again.

    Args:
        task_id: The parent session or task identifier.
        agent_id: The subagent's identifier.
    """
    _store.add(task_id, f"{_START_PREFIX}{agent_id}")


def has_agent_start(task_id: str) -> bool:
    """Check whether SubagentStart has recorded a subagent for a session.

    Args:
        task_id: The session or task identifier.

    Returns:
        True if at least one subagent id is recorded, so the frontend fires SubagentStart.
    """
    return any(entry.startswith(_START_PREFIX) for entry in _store.names(task_id))


def has_agent_use(task_id: str) -> bool:
    """Check whether any subagent-spawning tool was called for a session.

    Args:
        task_id: The session or task identifier.

    Returns:
        True if at least one agent tool was called.
    """
    return bool(_store.names(task_id))


def agent_use_count(task_id: str) -> int:
    """Return how many subagent-spawning tool calls were recorded for a session.

    Args:
        task_id: The session or task identifier.

    Returns:
        The total number of agent tool invocations recorded.
    """
    return len(_store.names(task_id))


def reset(task_id: str) -> None:
    """Clear recorded agent use for a session, and every per-agent entry under it.

    Args:
        task_id: The session or task identifier.
    """
    _store.reset(task_id)
