from __future__ import annotations

from cline_hooks.state.context import (
    _BAND_SIZE,
    _CONTEXT_THRESHOLD,
    reset,
    should_nudge_context,
)


class TestShouldNudgeContext:
    def test_below_threshold_no_nudge(self) -> None:
        assert should_nudge_context("t", _CONTEXT_THRESHOLD - 1) is False

    def test_at_threshold_fires(self) -> None:
        assert should_nudge_context("t", _CONTEXT_THRESHOLD) is True

    def test_does_not_refire_in_same_band(self) -> None:
        assert should_nudge_context("t", _CONTEXT_THRESHOLD) is True
        assert should_nudge_context("t", _CONTEXT_THRESHOLD + 1) is False
        assert should_nudge_context("t", _CONTEXT_THRESHOLD + _BAND_SIZE - 1) is False

    def test_fires_again_in_next_band(self) -> None:
        assert should_nudge_context("t", _CONTEXT_THRESHOLD) is True
        assert should_nudge_context("t", _CONTEXT_THRESHOLD + _BAND_SIZE) is True

    def test_fires_in_third_band(self) -> None:
        should_nudge_context("t", _CONTEXT_THRESHOLD)
        should_nudge_context("t", _CONTEXT_THRESHOLD + _BAND_SIZE)
        assert should_nudge_context("t", _CONTEXT_THRESHOLD + 2 * _BAND_SIZE) is True

    def test_jump_across_bands_fires_once_then_lower_bands_silent(self) -> None:
        assert should_nudge_context("t", _CONTEXT_THRESHOLD + 2 * _BAND_SIZE + 5) is True
        assert should_nudge_context("t", _CONTEXT_THRESHOLD + 10) is False

    def test_independent_sessions(self) -> None:
        assert should_nudge_context("a", _CONTEXT_THRESHOLD) is True
        assert should_nudge_context("b", _CONTEXT_THRESHOLD) is True

    def test_band_boundary_stays_in_band(self) -> None:
        assert should_nudge_context("t", _CONTEXT_THRESHOLD + _BAND_SIZE - 1) is True
        assert should_nudge_context("t", _CONTEXT_THRESHOLD) is False


class TestReset:
    def test_reset_allows_renudge(self) -> None:
        assert should_nudge_context("t", _CONTEXT_THRESHOLD) is True
        reset("t")
        assert should_nudge_context("t", _CONTEXT_THRESHOLD) is True

    def test_reset_nonexistent_is_noop(self) -> None:
        reset("nonexistent")

    def test_reset_does_not_affect_other_tasks(self) -> None:
        should_nudge_context("a", _CONTEXT_THRESHOLD)
        should_nudge_context("b", _CONTEXT_THRESHOLD)
        reset("a")
        assert should_nudge_context("b", _CONTEXT_THRESHOLD) is False
