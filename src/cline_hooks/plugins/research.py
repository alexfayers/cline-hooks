from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Any

from cline_hooks.core.parameters import WebResearchParameters
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.state import PluginStateStore
from cline_hooks.core.vocabulary import (
    NO_RESET_TASK_START_SOURCES,
    CanonicalHook,
    CanonicalTool,
)

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("hooks.ResearchPlugin")

WEB_RESEARCH_TOOLS = frozenset({CanonicalTool.WEB_FETCH, CanonicalTool.WEB_SEARCH})

RESEARCH_TRACE_CAP = 15

DEFAULT_RESEARCH_TRACE_HEADER = (
    "RESEARCH TRACE: MUST cite the lookups behind this turn's claims to the user, in ONE line only."
)

# Keyed by FrontendSpec.name; a frontend with no entry gets the default, which
# assumes nothing about where hook output surfaces.
RESEARCH_TRACE_HEADERS = {
    "claude-code": (
        "RESEARCH TRACE: MUST cite lookups behind this turn's claims, in ONE "
        "line only - the user already sees this hook's raw output."
    ),
    "kiro": (
        "RESEARCH TRACE: MUST start your reply with a line break, then write ONE "
        "line in exactly this format and nothing else: Sources: <tool> "
        '"<detail>", <tool> "<detail>", ... - substituting each tool/detail '
        "pair from the lookups below, copied verbatim, each detail written "
        "only once. No narration, no commentary, no parentheses, no restating "
        "a detail a second time."
    ),
}


@dataclass
class _ResearchState:
    """Research lookups recorded for a session."""

    records: list[dict[str, str]] = field(default_factory=list)


_store: PluginStateStore[_ResearchState] = PluginStateStore("research-state.json", _ResearchState)


def is_research_tool(tool_name: str, extra: frozenset[str]) -> bool:
    """Check whether a tool name counts as an external research lookup.

    Args:
        tool_name: The tool name as reported by the frontend.
        extra: Research tool names contributed by plugins.

    Returns:
        True if the tool fetches external information.
    """
    return tool_name in extra


def record_research(task_id: str, tool: str, detail: str) -> None:
    """Record that a research lookup was made for a session.

    Every lookup is recorded so the surfaced trace reflects the full set of
    external information gathered during the turn.

    Args:
        task_id: The session or task identifier.
        tool: The research tool that was called.
        detail: A short identifier for the lookup (e.g. a URL or query).
    """
    state = _store.get(task_id)
    state.records.append({"tool": tool, "detail": detail})
    _store.set(task_id, state)


def get_research(task_id: str) -> list[dict[str, str]]:
    """Return the research lookups recorded for a session.

    Args:
        task_id: The session or task identifier.

    Returns:
        A list of {"tool": ..., "detail": ...} records in call order.
    """
    return _store.get(task_id).records


def reset(task_id: str) -> None:
    """Clear recorded research for a session.

    Args:
        task_id: The session or task identifier.
    """
    _store.reset(task_id)


def get_all_research_tool_names(plugins: list[HooksPlugin]) -> frozenset[str]:
    """Collect research lookup tool names from all plugins.

    Args:
        plugins: Loaded plugin instances.

    Returns:
        Union of all plugin research tool name sets.
    """
    names: set[str] = set()
    for plugin in plugins:
        names.update(plugin.get_research_tool_names())
    return frozenset(names)


def get_all_research_detail_extractors(
    plugins: list[HooksPlugin],
) -> dict[str, Callable[[dict[str, Any]], str]]:
    """Collect research detail extractors from all plugins.

    Later plugins override earlier ones on key collision.

    Args:
        plugins: Loaded plugin instances.

    Returns:
        Merged mapping of tool name to detail-extraction callable.
    """
    extractors: dict[str, Callable[[dict[str, Any]], str]] = {}
    for plugin in plugins:
        extractors.update(plugin.get_research_detail_extractors())
    return extractors


def extract_research_detail(
    tool_name: str,
    parameters: dict[str, Any],
    extractors: dict[str, Callable[[dict[str, Any]], str]],
) -> str:
    """Return a short identifier for a research lookup.

    A plugin-supplied extractor for the tool takes precedence; extractors are
    third-party plugin code, so failures are caught and treated as no detail.
    Falls back to the built-in WebFetch/WebSearch handling.

    Args:
        tool_name: The research tool name.
        parameters: The tool parameters.
        extractors: Per-tool detail extractors contributed by plugins.

    Returns:
        A URL for WebFetch, a query for WebSearch, an extractor-derived string,
        otherwise an empty string.
    """
    extractor = extractors.get(tool_name)
    if extractor is not None:
        try:
            detail = extractor(parameters)
        except Exception:
            logger.exception("Research detail extractor for %s failed", tool_name)
            return ""
        return str(detail or "")
    if tool_name in WEB_RESEARCH_TOOLS:
        params = WebResearchParameters.build(parameters)
        return str(params.url if tool_name == CanonicalTool.WEB_FETCH else params.query)
    return ""


def record_research_use(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]
    task_id: str,
    tool_name: str,
    mcp_tool_name: str | None,
    arguments: dict[str, Any],
    research_names: frozenset[str],
    extractors: dict[str, Callable[[dict[str, Any]], str]],
) -> None:
    """Record a research lookup for a tool call, if it is one.

    Args:
        task_id: The session or task identifier.
        tool_name: The tool name as reported by the frontend.
        mcp_tool_name: The resolved MCP tool name, if this was an MCP call.
        arguments: The tool arguments (MCP arguments when applicable).
        research_names: Tool names that count as research lookups.
        extractors: Per-tool research detail extractors contributed by plugins.
    """
    research_tool = mcp_tool_name or tool_name
    if is_research_tool(research_tool, research_names):
        detail = extract_research_detail(research_tool, arguments, extractors)
        record_research(task_id, research_tool, detail)


def research_trace_header() -> str:
    """Return the Stop research-trace instruction header for the live frontend.

    Returns:
        The frontend's header, or DEFAULT_RESEARCH_TRACE_HEADER where it
        declares none.
    """
    spec = get_protocol().frontend_spec
    name = spec.name if spec else ""
    return RESEARCH_TRACE_HEADERS.get(name, DEFAULT_RESEARCH_TRACE_HEADER)


def format_research_trace(records: list[dict[str, str]], header: str) -> str:
    """Format recorded research lookups into a grouped, deduped, capped note.

    Detail lines are capped at RESEARCH_TRACE_CAP with a "(+N more)" note;
    tools whose lookups carried no detail still get a bare line, so their use
    is never silently dropped.

    Args:
        records: Research records in call order, each with "tool" and "detail".
        header: The protocol-specific instruction header to prepend.

    Returns:
        A RESEARCH TRACE note listing lookups grouped by tool, or an empty
        string if there are no records.
    """
    if not records:
        return ""

    grouped: dict[str, list[str]] = {}
    for record in records:
        details = grouped.setdefault(record["tool"], [])
        detail = record["detail"]
        if detail and detail not in details:
            details.append(detail)

    detail_lines: list[str] = []
    bare_lines: list[str] = []
    total_details = 0
    shown_details = 0
    for tool, details in grouped.items():
        if not details:
            bare_lines.append(f"- {tool}")
            continue
        total_details += len(details)
        room = RESEARCH_TRACE_CAP - shown_details
        if room <= 0:
            continue
        capped = details[:room]
        shown_details += len(capped)
        detail_lines.append(f"- {tool}: " + ", ".join(f'"{d}"' for d in capped))

    lines = [header, *detail_lines, *bare_lines]
    hidden = total_details - shown_details
    if hidden:
        lines.append(f"(+{hidden} more lookups not shown)")

    return "\n".join(lines)


class ResearchPlugin(HooksPlugin):
    """Supplies the default research tool set and emits the Stop research trace."""

    def get_research_tool_names(self) -> frozenset[str]:
        """Return the default set of research lookup tools.

        Returns:
            frozenset containing web_fetch and web_search.
        """
        return WEB_RESEARCH_TOOLS

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Emit the grouped research-citation trace on Stop.

        Args:
            hook_name: The hook event name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult carrying the trace note, or None if there is nothing
            to report.
        """
        if hook_name == CanonicalHook.TASK_START:
            task_id = kwargs.get("task_id")
            source = kwargs.get("source")
            if isinstance(task_id, str) and source not in NO_RESET_TASK_START_SOURCES:
                reset(task_id)
            return None
        if hook_name == CanonicalHook.TASK_COMPLETE:
            task_id = kwargs.get("task_id")
            if isinstance(task_id, str):
                reset(task_id)
            return None
        if hook_name != CanonicalHook.STOP:
            return None
        task_id = kwargs.get("task_id")
        if not isinstance(task_id, str):
            return None
        trace = format_research_trace(get_research(task_id), research_trace_header())
        reset(task_id)
        if not trace:
            return None
        return HookResult(notes=[trace])
