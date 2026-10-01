from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cline_hooks.core.plugin import HookResult
from cline_hooks.core.vocabulary import CanonicalHook
from cline_hooks.plugins.context_usage import (
    _BAND_SIZE,
    CONTEXT_REDUCED_THRESHOLD,
    ContextUsagePlugin,
    reset,
    should_nudge_context,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.conftest import StubTranscript


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


class TestTeammateWording:
    def test_teammate_gets_subagent_wording_from_main_token_source(
        self, stub_transcript: Callable[..., StubTranscript]
    ) -> None:
        stub_transcript(tokens=CONTEXT_REDUCED_THRESHOLD, subagent_tokens=0)
        result = ContextUsagePlugin().on_hook(
            CanonicalHook.POST_TOOL_USE,
            logger=logging.getLogger("test"),
            task_id="t",
            transcript_path="/tmp/transcript.jsonl",
            is_teammate=True,
        )
        assert isinstance(result, HookResult)
        assert f"{CONTEXT_REDUCED_THRESHOLD:,} tokens" in result.notes[0]
        assert "caller/lead" in result.notes[0]


class TestSubagentStopReset:
    def test_resets_subagent_scope_and_keeps_parent(self) -> None:
        should_nudge_context("t", _BAND_SIZE)
        should_nudge_context("t:a", _BAND_SIZE)
        ContextUsagePlugin().on_hook(
            CanonicalHook.SUBAGENT_STOP, logger=logging.getLogger("test"), agent_id="a", task_id="t:a"
        )
        assert should_nudge_context("t:a", _BAND_SIZE) is True
        assert should_nudge_context("t", _BAND_SIZE) is False

    def test_without_agent_id_is_noop(self) -> None:
        should_nudge_context("t:a", _BAND_SIZE)
        ContextUsagePlugin().on_hook(CanonicalHook.SUBAGENT_STOP, logger=logging.getLogger("test"), task_id="t:a")
        assert should_nudge_context("t:a", _BAND_SIZE) is False
