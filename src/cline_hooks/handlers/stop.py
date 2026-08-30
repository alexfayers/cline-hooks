from __future__ import annotations

import re
from typing import TYPE_CHECKING

from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.registry import hook_handler
from cline_hooks.core.response import allow, feedback
from cline_hooks.core.transcript import get_turn_assistant_text
import cline_hooks.state.research as research_state

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputStop

_RESEARCH_TRACE_CAP = 15

_DISMISSAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bpre-?existing (error|issue|bug|failure|problem)",
        r"\b(error|issue|bug|failure|problem) (is|was) pre-?existing\b",
        r"\bnot (caused|related to|introduced) by (my|this) (change|fix|commit|edit)",
        r"\bunrelated to (my|this|the current) change\b",
        r"\bnot something (i|we) (need|have) to fix\b",
        r"\bout of scope for this (change|fix|task)\b",
    ]
]

_DISMISSAL_NUDGE = (
    "DISMISSED ISSUE DETECTED: You described a problem as pre-existing/unrelated instead of "
    "fixing it. Unless the user has explicitly told you not to, MUST log a follow-up now "
    "(a memory task/ entity or TODO) so it isn't lost."
)


def _contains_dismissal_signal(message: str) -> bool:
    """Check if the assistant's last message dismisses an issue instead of fixing it.

    Args:
        message: The assistant's last response text.

    Returns:
        True if the message matches any dismissal-signal pattern.
    """
    return any(pattern.search(message) for pattern in _DISMISSAL_PATTERNS)


def _format_research_trace(records: list[dict[str, str]], header: str) -> str:
    """Format recorded research lookups into a grouped, deduped, capped note.

    Lookups are grouped by tool and deduped by detail. Detail lines are capped
    at _RESEARCH_TRACE_CAP with an explicit "(+N more lookups not shown)" note;
    tools whose lookups carried no detail (e.g. overlay-contributed tools) are
    always surfaced as a bare line so their use is never silently dropped.

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
        room = _RESEARCH_TRACE_CAP - shown_details
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


@hook_handler("Stop")
def handle_stop(hook: HookInputStop) -> None:
    """Handle Stop hook events: nudge on dismissed issues, force research citations.

    Args:
        hook: The hook input data.
    """
    if hook.stop and hook.stop.stopHookActive:
        allow()

    notes: list[str] = []
    if _contains_dismissal_signal(get_turn_assistant_text(hook.transcriptPath)):
        notes.append(_DISMISSAL_NUDGE)

    trace = _format_research_trace(research_state.get_research(hook.taskId), get_protocol().research_trace_header())
    research_state.reset(hook.taskId)
    if trace:
        notes.append(trace)

    if not notes:
        allow()

    feedback("\n\n".join(notes))
