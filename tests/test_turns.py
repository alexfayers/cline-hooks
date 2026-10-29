from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cline_hooks.core.protocol import RawPayload
from cline_hooks.core.vocabulary import CanonicalHook
from cline_hooks.plugins.nudges import (
    _AGENT_NUDGE_THRESHOLD,
    NudgesPlugin,
    increment,
    reset,
    should_nudge_agents,
)
from tests.conftest import CanonicalProtocol

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInput


def parse_data(raw: str) -> HookInput:
    return CanonicalProtocol().parse(RawPayload.from_stdin(raw))


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


class TestSubagentStopReset:
    def test_resets_subagent_scope_and_keeps_parent(self) -> None:
        increment("t")
        increment("t:a")
        NudgesPlugin().on_hook(
            CanonicalHook.SUBAGENT_STOP, logger=logging.getLogger("test"), agent_id="a", task_id="t:a"
        )
        assert increment("t:a") == 1
        assert increment("t") == 2

    def test_without_agent_id_is_noop(self) -> None:
        increment("t:a")
        NudgesPlugin().on_hook(CanonicalHook.SUBAGENT_STOP, logger=logging.getLogger("test"), task_id="t:a")
        assert increment("t:a") == 2
