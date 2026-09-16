from __future__ import annotations

from cline_hooks.state.delegation import reset, should_nudge_inline_work

_TASK = "task-1"


class TestShouldNudgeInlineWork:
    def test_fires_once_per_session(self) -> None:
        assert should_nudge_inline_work(_TASK) is True
        assert should_nudge_inline_work(_TASK) is False

    def test_isolated_per_task(self) -> None:
        should_nudge_inline_work(_TASK)
        assert should_nudge_inline_work("other-task") is True


class TestReset:
    def test_reset_allows_refire(self) -> None:
        should_nudge_inline_work(_TASK)
        reset(_TASK)
        assert should_nudge_inline_work(_TASK) is True

    def test_reset_does_not_affect_other_tasks(self) -> None:
        should_nudge_inline_work(_TASK)
        should_nudge_inline_work("other-task")
        reset(_TASK)
        assert should_nudge_inline_work("other-task") is False

    def test_reset_nonexistent_is_noop(self) -> None:
        reset("nonexistent")
