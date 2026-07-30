from __future__ import annotations

from cline_hooks.state.plan import (
    consume_plan_nudge,
    is_plan_exit_tool,
    record_plan_exit,
    reset,
)

_TASK = "task-1"


class TestIsPlanExitTool:
    def test_exit_plan_mode(self) -> None:
        assert is_plan_exit_tool("ExitPlanMode")

    def test_bash_is_not_plan_exit(self) -> None:
        assert not is_plan_exit_tool("Bash")

    def test_plan_mode_respond_is_not_plan_exit(self) -> None:
        assert not is_plan_exit_tool("plan_mode_respond")


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
