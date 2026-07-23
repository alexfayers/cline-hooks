from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.core.registry import hook_handler
from cline_hooks.core.response import allow, feedback
import cline_hooks.state.research as research_state

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputStop

_RESEARCH_TRACE_HEADER = (
    "RESEARCH TRACE: before finishing, cite the lookups that informed your "
    "work this turn, and note which came up empty."
)
_RESEARCH_TRACE_CAP = 15


def _format_research_trace(records: list[dict[str, str]]) -> str:
    """Format recorded research lookups into a grouped, deduped, capped note.

    Lookups are grouped by tool and deduped by detail. Detail lines are capped
    at _RESEARCH_TRACE_CAP with an explicit "(+N more lookups not shown)" note;
    tools whose lookups carried no detail (e.g. overlay-contributed tools) are
    always surfaced as a bare line so their use is never silently dropped.

    Args:
        records: Research records in call order, each with "tool" and "detail".

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
        room = _RESEARCH_TRACE_CAP - shown_details
        if room <= 0:
            continue
        capped = details[:room]
        shown_details += len(capped)
        detail_lines.append(f"- {tool}: " + ", ".join(f'"{d}"' for d in capped))

    lines = [_RESEARCH_TRACE_HEADER, *detail_lines, *bare_lines]
    hidden = total_details - shown_details
    if hidden:
        lines.append(f"(+{hidden} more lookups not shown)")

    return "\n".join(lines)


@hook_handler("Stop")
def handle_stop(hook: HookInputStop) -> None:
    """Handle Stop hook events by forcing a research-citation continuation.

    Args:
        hook: The hook input data.
    """
    if hook.stop and hook.stop.stopHookActive:
        allow()

    trace = _format_research_trace(research_state.get_research(hook.taskId))
    if not trace:
        allow()

    research_state.reset(hook.taskId)
    feedback(trace)
