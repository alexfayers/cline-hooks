from __future__ import annotations

from cline_hooks.handlers.context_nudge import context_note
from cline_hooks.state.agents import record_agent_use


class TestContextNote:
    def test_info_note_below_reduced_threshold(self) -> None:
        note = context_note("task-1", 150_000)
        assert note is not None
        assert "CONTEXT STATUS" in note
        assert "150,000" in note

    def test_reduced_note_on_first_crossing(self) -> None:
        note = context_note("task-1", 210_000)
        assert note is not None
        assert "Accuracy degrading" in note
        assert "210,000" in note

    def test_reduced_note_instructs_asking_before_new_work(self) -> None:
        note = context_note("task-1", 210_000)
        assert note is not None
        assert "Ask the user" in note

    def test_severe_note_on_first_crossing(self) -> None:
        note = context_note("task-1", 410_000)
        assert note is not None
        assert "badly degraded" in note
        assert "410,000" in note

    def test_reduced_note_does_not_refire_within_same_band(self) -> None:
        first = context_note("task-1", 210_000)
        assert first is not None
        second = context_note("task-1", 215_000)
        assert second is None

    def test_next_band_in_same_tier_omits_boundary_text(self) -> None:
        context_note("task-1", 210_000)
        note = context_note("task-1", 221_000)
        assert note is not None
        assert "Accuracy degrading" not in note
        assert "CONTEXT STATUS" in note
        assert "221,000" in note

    def test_crossing_into_severe_after_reduced_gets_severe_text(self) -> None:
        context_note("task-1", 210_000)
        note = context_note("task-1", 410_000)
        assert note is not None
        assert "badly degraded" in note

    def test_team_clause_appended_when_agent_used(self) -> None:
        record_agent_use("task-1", "Agent")
        note = context_note("task-1", 210_000)
        assert note is not None
        assert "TaskStop" in note

    def test_no_team_clause_when_no_agent(self) -> None:
        note = context_note("task-1", 210_000)
        assert note is not None
        assert "TaskStop" not in note
