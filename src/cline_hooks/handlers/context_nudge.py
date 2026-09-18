"""Shared agent-team-clause helper for handoff-style nudges."""

from __future__ import annotations

from cline_hooks.state.agents import has_agent_use

_TEAM_ACTIVE_CLAUSE = (
    "An agent team appears to be active this session. Before handing off, MUST collect each teammate's progress "
    "into memory/TODOs and stop the team so it does not keep running after this session ends."
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
