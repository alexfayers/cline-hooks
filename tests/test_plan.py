from __future__ import annotations

import logging

from cline_hooks.core.vocabulary import CanonicalHook
from cline_hooks.plugins.plan_handoff import (
    PlanHandoffPlugin,
    consume_plan_nudge,
    is_plan_exit_tool,
    record_plan_exit,
    reset,
)

_TASK = "task-1"


class TestIsPlanExitTool:
    def test_exit_plan_mode(self) -> None:
        assert is_plan_exit_tool("exit_plan_mode")

    def test_bash_is_not_plan_exit(self) -> None:
        assert not is_plan_exit_tool("Bash")

    def test_plan_mode_respond_is_plan_exit(self) -> None:
        assert is_plan_exit_tool("plan_mode_respond")


class TestConsumePlanNudge:
    def test_no_nudge_initially(self) -> None:
        assert consume_plan_nudge(_TASK) is False

    def test_fires_once_after_plan_exit(self) -> None:
        record_plan_exit(_TASK)
        assert consume_plan_nudge(_TASK) is True
        assert consume_plan_nudge(_TASK) is False

    def test_refires_after_second_plan_exit(self) -> None:
        record_plan_exit(_TASK)
        assert consume_plan_nudge(_TASK) is True
        record_plan_exit(_TASK)
        assert consume_plan_nudge(_TASK) is True

    def test_isolated_per_task(self) -> None:
        record_plan_exit(_TASK)
        assert consume_plan_nudge("other-task") is False


class TestReset:
    def test_reset_clears_pending_nudge(self) -> None:
        record_plan_exit(_TASK)
        reset(_TASK)
        assert consume_plan_nudge(_TASK) is False

    def test_reset_nonexistent_is_noop(self) -> None:
        reset("nonexistent")


class TestSubagentStop:
    def test_subagent_stop_resets_only_subagent_state(self) -> None:
        record_plan_exit("task-1:a")
        record_plan_exit(_TASK)
        PlanHandoffPlugin().on_hook(
            CanonicalHook.SUBAGENT_STOP, logger=logging.getLogger("test"), task_id="task-1:a", agent_id="a"
        )
        assert consume_plan_nudge("task-1:a") is False
        assert consume_plan_nudge(_TASK) is True

    def test_subagent_stop_without_agent_id_is_noop(self) -> None:
        record_plan_exit("task-1:a")
        PlanHandoffPlugin().on_hook(CanonicalHook.SUBAGENT_STOP, logger=logging.getLogger("test"), task_id="task-1:a")
        assert consume_plan_nudge("task-1:a") is True
