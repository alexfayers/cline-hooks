"""Shared context-usage nudge logic, called from both UserPromptSubmit and PostToolUse."""

from __future__ import annotations

from cline_hooks.state.agents import has_agent_use
from cline_hooks.state.context import (
    CONTEXT_DEGRADED_THRESHOLD,
    CONTEXT_REDUCED_THRESHOLD,
    crossed_boundary,
    should_nudge_context,
)

_CONTEXT_STATUS = "CONTEXT STATUS: ~{tokens:,} tokens in use."

_CONTEXT_NUDGE_INFO = f"{_CONTEXT_STATUS} No action needed yet."

_CONTEXT_NUDGE_REDUCED = (
    f"{_CONTEXT_STATUS} Accuracy degrading past {CONTEXT_REDUCED_THRESHOLD // 1000}k. MUST ask the user before "
    "starting new planning or implementation. To continue, MUST record current state in memory."
)

_CONTEXT_NUDGE_SEVERE = (
    f"{_CONTEXT_STATUS} Accuracy badly degraded. MUST push back on new work - record current state in memory "
    "and hand off to a fresh session unless told to continue."
)

_TEAM_ACTIVE_CLAUSE = (
    "An agent team appears to be active this session. Before handing off, MUST collect each teammate's progress "
    "into memory/TODOs and stop the team (TaskStop) so it does not keep running after this session ends."
)


def with_team_clause(note: str, task_id: str) -> str:
    """Append the agent-team-stop clause to a nudge when a team is active.

    Args:
        note: The base nudge text.
        task_id: The session or task identifier.

    Returns:
        The note, with the team clause appended when an agent team is active.
    """
    if has_agent_use(task_id):
        return f"{note}\n\n{_TEAM_ACTIVE_CLAUSE}"
    return note


def context_note(task_id: str, token_count: int) -> str | None:
    """Return the context-usage nudge for the current token count, or None.

    Fires at most once per 10k-token band for the session, from whichever call
    site (UserPromptSubmit or PostToolUse) reaches that band first. The longer
    accuracy/action text for a degradation tier is appended only on the note
    that first crosses into that tier (CONTEXT_REDUCED_THRESHOLD or
    CONTEXT_DEGRADED_THRESHOLD) - subsequent same-tier notes stay short.

    Args:
        task_id: The session or task identifier.
        token_count: The current context token count.

    Returns:
        The nudge text, or None when nothing should fire this check.
    """
    if not should_nudge_context(task_id, token_count):
        return None
    boundary = crossed_boundary(task_id, token_count)
    if boundary == CONTEXT_DEGRADED_THRESHOLD:
        return with_team_clause(_CONTEXT_NUDGE_SEVERE.format(tokens=token_count), task_id)
    if boundary == CONTEXT_REDUCED_THRESHOLD:
        return with_team_clause(_CONTEXT_NUDGE_REDUCED.format(tokens=token_count), task_id)
    return _CONTEXT_NUDGE_INFO.format(tokens=token_count)
