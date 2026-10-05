from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import TYPE_CHECKING, Any

from cline_hooks.core.parameters import WebResearchParameters
from cline_hooks.core.plugin import HookResult, HooksPlugin, collect_contributions, hookimpl, hookspec
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


def record_research(task_id: str, tool: str, detail: str) -> None:
    """Record that a research lookup was made for a session.

    Every lookup is recorded so the surfaced trace reflects the full set of
    external information gathered during the turn.

    Args:
        task_id: The session or task identifier.
        tool: The research tool that was called.
        detail: A short identifier for the lookup (e.g. a URL or query).
    """

    def append(state: _ResearchState) -> None:
        state.records.append({"tool": tool, "detail": detail})

    _store.update(task_id, append)


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


def drain_research(task_id: str) -> list[dict[str, str]]:
    """Remove and return the research lookups recorded for a session and its subagents.

    Args:
        task_id: The session or task identifier.

    Returns:
        A list of {"tool": ..., "detail": ...} records, the session's own first.
    """
    return [record for state in _store.drain(task_id) for record in state.records]


class ResearchSpec:
    """Extension point for contributing research lookup tools."""

    @hookspec
    def research_tools(self) -> dict[str, Callable[[dict[str, Any]], str]]:
        """Return the tools that count as research lookups, with their detail extractors.

        Each tool name maps to a callable that derives a short detail string (e.g. a URL
        or query) from that tool's arguments; MCP arguments for MCP tools.

        Returns:
            Mapping of tool name to a detail-extraction callable.
        """
        raise NotImplementedError


def record_research_use(
    task_id: str,
    tool_name: str,
    mcp_tool_name: str | None,
    arguments: dict[str, Any],
) -> None:
    """Record a research lookup for a tool call, if a plugin contributes it as one.

    The first contributor of the tool name supplies the detail extractor; extractors
    are third-party plugin code, so a failing extractor is logged and records no detail.

    Args:
        task_id: The session or task identifier.
        tool_name: The tool name as reported by the frontend.
        mcp_tool_name: The resolved MCP tool name, if this was an MCP call.
        arguments: The tool arguments (MCP arguments when applicable).
    """
    research_tool = mcp_tool_name or tool_name
    for tools in collect_contributions(ResearchSpec.research_tools, dict):
        extractor = tools.get(research_tool)
        if extractor is None:
            continue
        try:
            detail = str(extractor(arguments) or "")
        except Exception:
            logger.exception("Research detail extractor for %s failed", research_tool)
            detail = ""
        record_research(task_id, research_tool, detail)
        return


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

    hookspecs = ResearchSpec

    @hookimpl
    def research_tools(self) -> dict[str, Callable[[dict[str, Any]], str]]:
        """Return the web lookup tools with their URL and query extractors.

        Returns:
            Mapping of web_fetch and web_search to their detail extractors.
        """
        return {
            CanonicalTool.WEB_FETCH: lambda parameters: str(WebResearchParameters.build(parameters).url),
            CanonicalTool.WEB_SEARCH: lambda parameters: str(WebResearchParameters.build(parameters).query),
        }

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
        trace = format_research_trace(drain_research(task_id), research_trace_header())
        if not trace:
            return None
        return HookResult(notes=[trace])
