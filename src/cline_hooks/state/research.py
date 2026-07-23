"""Track external research lookups made during a session."""

from __future__ import annotations

import json
import logging

from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks")

_STATE_PATH = get_data_dir() / "research-state.json"

DEFAULT_RESEARCH_TOOLS: frozenset[str] = frozenset({
    "WebFetch",
    "WebSearch",
})


def _read() -> dict[str, list[dict[str, str]]]:
    try:
        return dict(json.loads(_STATE_PATH.read_text()))
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def _write(data: dict[str, list[dict[str, str]]]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(data))


def is_research_tool(tool_name: str, extra: frozenset[str]) -> bool:
    """Check whether a tool name counts as an external research lookup.

    Args:
        tool_name: The tool name as reported by the frontend.
        extra: Additional research tool names contributed by plugins.

    Returns:
        True if the tool fetches external information.
    """
    return tool_name in DEFAULT_RESEARCH_TOOLS or tool_name in extra


def record_research(task_id: str, tool: str, detail: str) -> None:
    """Record that a research lookup was made for a session.

    Every lookup is recorded so the surfaced trace reflects the full set of
    external information gathered during the turn.

    Args:
        task_id: The session or task identifier.
        tool: The research tool that was called.
        detail: A short identifier for the lookup (e.g. a URL or query).
    """
    data = _read()
    data[task_id] = [*data.get(task_id, []), {"tool": tool, "detail": detail}]
    _write(data)


def get_research(task_id: str) -> list[dict[str, str]]:
    """Return the research lookups recorded for a session.

    Args:
        task_id: The session or task identifier.

    Returns:
        A list of {"tool": ..., "detail": ...} records in call order.
    """
    return _read().get(task_id, [])


def reset(task_id: str) -> None:
    """Clear recorded research for a session.

    Args:
        task_id: The session or task identifier.
    """
    data = _read()
    if task_id in data:
        del data[task_id]
        _write(data)
