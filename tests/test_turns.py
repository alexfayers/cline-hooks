from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest

from cline_hooks.frontends.cline import parse_cline_data as parse_data
from cline_hooks.handlers.user_prompt import handle_user_prompt_submit
from cline_hooks.state.turns import (
    _AGENT_NUDGE_THRESHOLD,
    _REMINDER_INTERVAL,
    _SCOPE_CHECK_THRESHOLD,
    increment,
    reset,
    should_nudge_agents,
    should_remind,
)

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputUserPromptSubmit

_BASE = {
    "clineVersion": "1.0.0",
    "timestamp": "0",
    "taskId": "task-turns",
    "userId": "user-1",
    "workspaceRoots": [],
    "hookName": "UserPromptSubmit",
}


class TestIncrement:
    def test_starts_at_one(self) -> None:
        assert increment("t1") == 1

    def test_increments_sequentially(self) -> None:
        for i in range(1, 6):
            assert increment("t2") == i

    def test_independent_sessions(self) -> None:
        increment("a")
        increment("a")
        assert increment("b") == 1
        assert increment("a") == 3


class TestShouldRemind:
    def test_below_threshold_no_reminder(self) -> None:
        for i in range(1, _SCOPE_CHECK_THRESHOLD):
            assert should_remind(i) is False

    def test_at_threshold_fires(self) -> None:
        assert should_remind(_SCOPE_CHECK_THRESHOLD) is True

    def test_fires_at_intervals_after_threshold(self) -> None:
        assert should_remind(_SCOPE_CHECK_THRESHOLD + _REMINDER_INTERVAL) is True
        assert should_remind(_SCOPE_CHECK_THRESHOLD + 2 * _REMINDER_INTERVAL) is True

    def test_does_not_fire_between_intervals(self) -> None:
        assert should_remind(_SCOPE_CHECK_THRESHOLD + 1) is False
        assert should_remind(_SCOPE_CHECK_THRESHOLD + _REMINDER_INTERVAL - 1) is False


class TestShouldNudgeAgents:
    def test_below_threshold_no_nudge(self) -> None:
        for i in range(1, _AGENT_NUDGE_THRESHOLD):
            assert should_nudge_agents(i, 0) is False

    def test_at_threshold_fires_when_no_agents(self) -> None:
        assert should_nudge_agents(_AGENT_NUDGE_THRESHOLD, 0) is True

    def test_at_threshold_silent_when_rate_met(self) -> None:
        assert should_nudge_agents(_AGENT_NUDGE_THRESHOLD, 1) is False

    def test_only_fires_on_checkpoints(self) -> None:
        assert should_nudge_agents(_AGENT_NUDGE_THRESHOLD + 1, 0) is False
        assert should_nudge_agents(2 * _AGENT_NUDGE_THRESHOLD - 1, 0) is False

    def test_refires_when_rate_lags_as_session_grows(self) -> None:
        # Used one agent early then ran long: rate falls behind, nudge returns.
        assert should_nudge_agents(2 * _AGENT_NUDGE_THRESHOLD, 1) is True
        assert should_nudge_agents(6 * _AGENT_NUDGE_THRESHOLD, 1) is True

    def test_silent_when_rate_kept_up(self) -> None:
        assert should_nudge_agents(2 * _AGENT_NUDGE_THRESHOLD, 2) is False
        assert should_nudge_agents(6 * _AGENT_NUDGE_THRESHOLD, 6) is False


class TestReset:
    def test_reset_clears_count(self) -> None:
        for _ in range(5):
            increment("r1")
        reset("r1")
        assert increment("r1") == 1

    def test_reset_nonexistent_is_noop(self) -> None:
        reset("nonexistent")


class TestIntegration:
    def _run_n_turns(self, n: int) -> dict[str, object] | None:
        """Run n turns and return the output from the last one."""
        last_output: dict[str, object] | None = None
        for _ in range(n):
            hook = cast(
                "HookInputUserPromptSubmit",
                parse_data(
                    json.dumps({
                        **_BASE,
                        "userPromptSubmit": {"userMessage": "neutral"},
                    })
                ),
            )
            output: list[str] = []
            try:
                with (
                    patch("builtins.print", side_effect=lambda s, _out=output, **kw: _out.append(s)),
                    patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
                    patch("cline_hooks.handlers.user_prompt.datetime") as mock_dt,
                ):
                    mock_dt.now.return_value.hour = 12
                    handle_user_prompt_submit(hook)
            except SystemExit:
                pass
            if output:
                last_output = cast("dict[str, object]", json.loads(output[0]))
            else:
                last_output = None
        return last_output

    def test_no_reminder_before_threshold(self) -> None:
        result = self._run_n_turns(_SCOPE_CHECK_THRESHOLD - 1)
        assert result is None

    def test_reminder_at_threshold(self) -> None:
        result = self._run_n_turns(_SCOPE_CHECK_THRESHOLD)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "SESSION LENGTH CHECK" in context
        assert str(_SCOPE_CHECK_THRESHOLD) in context

    @pytest.mark.parametrize("extra", [_REMINDER_INTERVAL, 2 * _REMINDER_INTERVAL])
    def test_reminder_repeats_at_intervals(self, extra: int) -> None:
        result = self._run_n_turns(_SCOPE_CHECK_THRESHOLD + extra)
        assert result is not None
        assert "SESSION LENGTH CHECK" in cast("str", result.get("contextModification", ""))
