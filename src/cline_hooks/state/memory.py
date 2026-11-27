"""Track memory-server availability and memory-write MCP tool calls during a session."""

from __future__ import annotations

import logging
from typing import cast

from cline_hooks.state.jsonfile import discard_key, discard_prefix, read_json, updated_json
from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks.state.memory")

_STATE_PATH = get_data_dir() / "memory-state.json"
_AVAILABLE_PATH = get_data_dir() / "memory-available.json"

_MEMORY_WRITE_TOOLS: frozenset[str] = frozenset({
    "create_entities",
    "add_observations",
    "set_entity_status",
    "create_relations",
    "delete_entity",
    "delete_observations",
    "delete_relation",
})

_MEMORY_TOOLS: frozenset[str] = _MEMORY_WRITE_TOOLS | {"read_graph", "search_nodes", "get_entity_with_relations"}


def _session_key(task_id: str) -> str:
    return task_id.split(":", 1)[0]


def record_mcp_call(task_id: str, server_name: str, tool_name: str) -> None:
    """Mark the memory server available for a session when a successful MCP call reached it.

    Args:
        task_id: The session or per-agent state key.
        server_name: The MCP server name.
        tool_name: The normalised MCP tool name.
    """
    if "memory" in server_name.lower() or tool_name in _MEMORY_TOOLS:
        with updated_json(_AVAILABLE_PATH, cast("dict[str, bool]", {})) as data:
            data[_session_key(task_id)] = True


def memory_available(task_id: str) -> bool:
    """Check whether a memory server has responded in a session, so memory reminders apply.

    Args:
        task_id: The session or per-agent state key.

    Returns:
        True once a memory MCP call has succeeded in the session.
    """
    data: dict[str, bool] = read_json(_AVAILABLE_PATH, {})
    return data.get(_session_key(task_id), False)


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
    with updated_json(_STATE_PATH, cast("dict[str, list[str]]", {})) as data:
        writes = set(data.get(task_id, []))
        writes.add(tool_name)
        data[task_id] = sorted(writes)


def has_memory_writes(task_id: str) -> bool:
    """Check whether any memory-write tools were called for a session.

    Args:
        task_id: The session or task identifier.

    Returns:
        True if at least one memory-write tool was called.
    """
    data: dict[str, list[str]] = read_json(_STATE_PATH, {})
    return bool(data.get(task_id))


def reset(task_id: str) -> None:
    """Clear recorded memory writes for a session, and every per-agent entry under it.

    Args:
        task_id: The session or task identifier.
    """
    discard_key(_STATE_PATH, task_id)
    discard_prefix(_STATE_PATH, f"{task_id}:")
    discard_key(_AVAILABLE_PATH, task_id)
