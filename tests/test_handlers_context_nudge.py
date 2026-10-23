from __future__ import annotations

import pytest

from cline_hooks.plugins.context_usage import (
    _BAND_SIZE,
    CONTEXT_DEGRADED_THRESHOLD,
    CONTEXT_REDUCED_THRESHOLD,
    context_note,
)
from cline_hooks.state.agents import record_agent_use

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
        assert "Context budget exhausted" in note
        assert f"{_JUST_ABOVE_SEVERE:,}" in note

    def test_reduced_note_does_not_refire_within_same_band(self) -> None:
        first = context_note("task-1", _JUST_ABOVE_REDUCED)
        assert first is not None
        second = context_note("task-1", _SAME_BAND_AS_REDUCED)
        assert second is None

    @pytest.mark.parametrize(
        ("token_count", "directive"),
        [
            (_NEXT_BAND_AFTER_REDUCED, "MUST ask the user"),
            (CONTEXT_DEGRADED_THRESHOLD - 1, "MUST ask the user"),
            (_JUST_ABOVE_SEVERE + _BAND_SIZE, "Context budget exhausted"),
            (CONTEXT_DEGRADED_THRESHOLD, "Context budget exhausted"),
        ],
    )
    def test_every_note_in_a_tier_carries_the_tier_directive(self, token_count: int, directive: str) -> None:
        context_note("task-1", 0)
        note = context_note("task-1", token_count)
        assert note is not None
        assert directive in note
        assert "No action needed yet" not in note

    def test_crossing_into_severe_after_reduced_gets_severe_text(self) -> None:
        context_note("task-1", _JUST_ABOVE_REDUCED)
        note = context_note("task-1", _JUST_ABOVE_SEVERE)
        assert note is not None
        assert "Context budget exhausted" in note

    def test_team_clause_appended_when_agent_used(self) -> None:
        record_agent_use("task-1", "Agent")
        note = context_note("task-1", _JUST_ABOVE_REDUCED)
        assert note is not None
        assert "stop the team" in note

    def test_no_team_clause_when_no_agent(self) -> None:
        note = context_note("task-1", _JUST_ABOVE_REDUCED)
        assert note is not None
        assert "stop the team" not in note


class TestContextNoteWindow:
    def test_info_note_shows_tokens_window_and_percent(self) -> None:
        note = context_note("task-1", 210_000, context_window=1_000_000)
        assert note is not None
        assert "210,000 / 500,000 tokens (42.0%)" in note

    def test_unknown_window_keeps_the_plain_wording(self) -> None:
        note = context_note("task-1", 210_000, context_window=None)
        assert note is not None
        assert "~210,000 tokens in use" in note
        assert "%" not in note

    def test_large_window_keeps_the_absolute_thresholds(self) -> None:
        note = context_note("task-1", _JUST_ABOVE_REDUCED, context_window=1_000_000)
        assert note is not None
        assert "Accuracy degrading past 300k" in note

    def test_small_window_keeps_the_absolute_thresholds(self) -> None:
        note = context_note("task-1", 180_000, context_window=200_000)
        assert note is not None
        assert "90.0%" in note
        assert "No action needed yet" in note

    def test_subagent_note_shows_window_too(self) -> None:
        note = context_note("task-1:sub-1", _JUST_ABOVE_REDUCED, is_subagent=True, context_window=1_000_000)
        assert note is not None
        assert "310,000 / 500,000 tokens (62.0%)" in note
        assert "report your state to your caller/lead" in note


class TestContextNoteSubagent:
    def test_reduced_note_instructs_reporting_to_caller(self) -> None:
        note = context_note("task-1:sub-1", _JUST_ABOVE_REDUCED, is_subagent=True)
        assert note is not None
        assert "report your state to your caller/lead" in note
        assert "MUST ask the user" not in note

    def test_severe_note_instructs_reporting_to_caller(self) -> None:
        note = context_note("task-1:sub-1", _JUST_ABOVE_SEVERE, is_subagent=True)
        assert note is not None
        assert "report your state to your caller/lead" in note
        assert "hand off to a fresh session" not in note

    def test_no_team_clause_even_when_agent_used(self) -> None:
        record_agent_use("task-1:sub-1", "Agent")
        note = context_note("task-1:sub-1", _JUST_ABOVE_REDUCED, is_subagent=True)
        assert note is not None
        assert "stop the team" not in note
