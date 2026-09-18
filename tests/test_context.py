from __future__ import annotations

from cline_hooks.plugins.context_usage import (
    _BAND_SIZE,
    reset,
    should_nudge_context,
)


class TestShouldNudgeContext:
    def test_fires_at_zero(self) -> None:
        assert should_nudge_context("t", 0) is True

    def test_fires_first_band(self) -> None:
        assert should_nudge_context("t", 5_000) is True

    def test_does_not_refire_in_same_band(self) -> None:
        assert should_nudge_context("t", 5_000) is True
        assert should_nudge_context("t", 5_001) is False
        assert should_nudge_context("t", _BAND_SIZE - 1) is False

    def test_fires_again_in_next_band(self) -> None:
        assert should_nudge_context("t", 5_000) is True
        assert should_nudge_context("t", _BAND_SIZE) is True

    def test_fires_in_third_band(self) -> None:
        should_nudge_context("t", 0)
        should_nudge_context("t", _BAND_SIZE)
        assert should_nudge_context("t", 2 * _BAND_SIZE) is True

    def test_jump_across_bands_fires_once_then_lower_bands_silent(self) -> None:
        assert should_nudge_context("t", 3 * _BAND_SIZE + 5) is True
        assert should_nudge_context("t", _BAND_SIZE) is False

    def test_independent_sessions(self) -> None:
        assert should_nudge_context("a", _BAND_SIZE) is True
        assert should_nudge_context("b", _BAND_SIZE) is True

    def test_band_boundary_stays_in_band(self) -> None:
        assert should_nudge_context("t", _BAND_SIZE + 5) is True
        assert should_nudge_context("t", _BAND_SIZE + 6) is False


class TestReset:
    def test_reset_allows_renudge(self) -> None:
        assert should_nudge_context("t", _BAND_SIZE) is True
        reset("t")
        assert should_nudge_context("t", _BAND_SIZE) is True

    def test_reset_nonexistent_is_noop(self) -> None:
        reset("nonexistent")

    def test_reset_does_not_affect_other_tasks(self) -> None:
        should_nudge_context("a", _BAND_SIZE)
        should_nudge_context("b", _BAND_SIZE)
        reset("a")
        assert should_nudge_context("b", _BAND_SIZE) is False
