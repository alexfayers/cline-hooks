"""Track whether memory-write MCP tools were called during a session."""

from __future__ import annotations

import json
import logging

from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks")

_STATE_PATH = get_data_dir() / "memory-state.json"

_MEMORY_WRITE_TOOLS: frozenset[str] = frozenset({
    "create_entities",
    "add_observations",
    "set_entity_status",
    "create_relations",
    "delete_entity",
    "delete_observations",
    "delete_relation",
})


def _read() -> dict[str, list[str]]:
    try:
        return dict(json.loads(_STATE_PATH.read_text()))
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def _write(data: dict[str, list[str]]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(data))


def _extract_tool_suffix(tool_name: str) -> str:
    """Extract the bare tool name from a prefixed MCP tool call.

    Handles both Cline format ("create_entities") and Claude Code format
    ("mcp__memory__create_entities").

    Args:
        tool_name: The tool name as reported by the frontend.

    Returns:
        The bare tool name suffix.
    """
    if "__" in tool_name:
        return tool_name.rsplit("__", 1)[-1]
    return tool_name


def is_memory_write(tool_name: str) -> bool:
    """Check whether a tool name is a memory-write operation.

    Args:
        tool_name: The tool name (e.g. "create_entities" or "mcp__memory__create_entities").

    Returns:
        True if the tool is a memory-write operation.
    """
    return _extract_tool_suffix(tool_name) in _MEMORY_WRITE_TOOLS


def record_memory_write(task_id: str, tool_name: str) -> None:
    """Record that a memory-write tool was called for a session.

    Args:
        task_id: The session or task identifier.
        tool_name: The memory-write tool that was called.
    """
    data = _read()
    writes = set(data.get(task_id, []))
    writes.add(tool_name)
    data[task_id] = sorted(writes)
    _write(data)


def has_memory_writes(task_id: str) -> bool:
    """Check whether any memory-write tools were called for a session.

    Args:
        task_id: The session or task identifier.

    Returns:
        True if at least one memory-write tool was called.
    """
    return bool(_read().get(task_id))


def reset(task_id: str) -> None:
    """Clear recorded memory writes for a session.

    Args:
        task_id: The session or task identifier.
    """
    data = _read()
    if task_id in data:
        del data[task_id]
        _write(data)
