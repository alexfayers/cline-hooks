from __future__ import annotations

from cline_hooks.handlers.context_nudge import context_note
from cline_hooks.state.agents import record_agent_use
from cline_hooks.state.context import (
    _BAND_SIZE,
    CONTEXT_DEGRADED_THRESHOLD,
    CONTEXT_REDUCED_THRESHOLD,
)

_BELOW_REDUCED = CONTEXT_REDUCED_THRESHOLD // 2
_JUST_ABOVE_REDUCED = CONTEXT_REDUCED_THRESHOLD + _BAND_SIZE
_SAME_BAND_AS_REDUCED = _JUST_ABOVE_REDUCED + _BAND_SIZE // 2
_NEXT_BAND_AFTER_REDUCED = _JUST_ABOVE_REDUCED + _BAND_SIZE + 1_000
_JUST_ABOVE_SEVERE = CONTEXT_DEGRADED_THRESHOLD + _BAND_SIZE


class TestContextNote:
    def test_info_note_below_reduced_threshold(self) -> None:
        note = context_note("task-1", _BELOW_REDUCED)
        assert note is not None
        assert "CONTEXT STATUS" in note
        assert f"{_BELOW_REDUCED:,}" in note

    def test_reduced_note_on_first_crossing(self) -> None:
        note = context_note("task-1", _JUST_ABOVE_REDUCED)
        assert note is not None
        assert "Accuracy degrading" in note
        assert f"{_JUST_ABOVE_REDUCED:,}" in note

    def test_reduced_note_instructs_asking_before_new_work(self) -> None:
        note = context_note("task-1", _JUST_ABOVE_REDUCED)
        assert note is not None
        assert "MUST ask the user" in note

    def test_severe_note_on_first_crossing(self) -> None:
        note = context_note("task-1", _JUST_ABOVE_SEVERE)
        assert note is not None
        assert "badly degraded" in note
        assert f"{_JUST_ABOVE_SEVERE:,}" in note

    def test_reduced_note_does_not_refire_within_same_band(self) -> None:
        first = context_note("task-1", _JUST_ABOVE_REDUCED)
        assert first is not None
        second = context_note("task-1", _SAME_BAND_AS_REDUCED)
        assert second is None

    def test_next_band_in_same_tier_omits_boundary_text(self) -> None:
        context_note("task-1", _JUST_ABOVE_REDUCED)
        note = context_note("task-1", _NEXT_BAND_AFTER_REDUCED)
        assert note is not None
        assert "Accuracy degrading" not in note
        assert "CONTEXT STATUS" in note
        assert f"{_NEXT_BAND_AFTER_REDUCED:,}" in note

    def test_crossing_into_severe_after_reduced_gets_severe_text(self) -> None:
        context_note("task-1", _JUST_ABOVE_REDUCED)
        note = context_note("task-1", _JUST_ABOVE_SEVERE)
        assert note is not None
        assert "badly degraded" in note

    def test_team_clause_appended_when_agent_used(self) -> None:
        record_agent_use("task-1", "Agent")
        note = context_note("task-1", _JUST_ABOVE_REDUCED)
        assert note is not None
        assert "TaskStop" in note

    def test_no_team_clause_when_no_agent(self) -> None:
        note = context_note("task-1", _JUST_ABOVE_REDUCED)
        assert note is not None
        assert "TaskStop" not in note
