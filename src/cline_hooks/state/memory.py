"""Track whether memory-write MCP tools were called during a session."""

from __future__ import annotations

import logging

from cline_hooks.core.state import NameStore

logger = logging.getLogger("hooks.state.memory")

_store = NameStore("memory-state.json")

_MEMORY_WRITE_TOOLS: frozenset[str] = frozenset({
    "create_entities",
    "add_observations",
    "set_entity_status",
    "create_relations",
    "delete_entity",
    "delete_observations",
    "delete_relation",
})


def is_memory_write(tool_name: str) -> bool:
    """Check whether a tool name is a memory-write operation.

    Args:
        tool_name: The normalised MCP tool name (e.g. "create_entities").

    Returns:
        True if the tool is a memory-write operation.
    """
    return tool_name in _MEMORY_WRITE_TOOLS


def record_memory_write(task_id: str, tool_name: str) -> None:
    """Record that a memory-write tool was called for a session.

    Args:
        task_id: The session or task identifier.
        tool_name: The memory-write tool that was called.
    """
    _store.add(task_id, tool_name)


def has_memory_writes(task_id: str) -> bool:
    """Check whether any memory-write tools were called for a session.

    Args:
        task_id: The session or task identifier.

    Returns:
        True if at least one memory-write tool was called.
    """
    return bool(_store.names(task_id))


def reset(task_id: str) -> None:
    """Clear recorded memory writes for a session, and every per-agent entry under it.

    Args:
        task_id: The session or task identifier.
    """
    _store.reset(task_id)
