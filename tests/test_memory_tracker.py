from __future__ import annotations

import cline_hooks.memory_tracker as module
from cline_hooks.memory_tracker import clear, increment, reset, should_block

_TASK = "task-1"


class TestIncrement:
    def test_starts_at_zero(self) -> None:
        assert not should_block(_TASK, threshold=1)

    def test_increment_returns_new_value(self) -> None:
        assert increment(_TASK) == 1

    def test_increment_accumulates(self) -> None:
        increment(_TASK)
        increment(_TASK)
        assert increment(_TASK) == 3

    def test_tasks_tracked_independently(self) -> None:
        increment(_TASK)
        increment(_TASK)
        increment("other")
        assert increment("other") == 2


class TestShouldBlock:
    def test_does_not_block_below_threshold(self) -> None:
        for _ in range(9):
            increment(_TASK)
        assert not should_block(_TASK, threshold=10)

    def test_blocks_at_threshold(self) -> None:
        for _ in range(10):
            increment(_TASK)
        assert should_block(_TASK, threshold=10)

    def test_blocks_above_threshold(self) -> None:
        for _ in range(15):
            increment(_TASK)
        assert should_block(_TASK, threshold=10)

    def test_uses_default_threshold(self) -> None:
        for _ in range(module._MEMORY_BLOCK_THRESHOLD):
            increment(_TASK)
        assert should_block(_TASK)

    def test_unknown_task_does_not_block(self) -> None:
        assert not should_block("unknown-task")


class TestReset:
    def test_reset_clears_counter(self) -> None:
        for _ in range(10):
            increment(_TASK)
        reset(_TASK)
        assert not should_block(_TASK)

    def test_reset_does_not_affect_other_tasks(self) -> None:
        for _ in range(10):
            increment(_TASK)
            increment("other")
        reset(_TASK)
        assert should_block("other")

    def test_can_increment_after_reset(self) -> None:
        for _ in range(10):
            increment(_TASK)
        reset(_TASK)
        assert increment(_TASK) == 1


class TestClear:
    def test_clear_removes_task(self) -> None:
        for _ in range(10):
            increment(_TASK)
        clear(_TASK)
        assert not should_block(_TASK)

    def test_clear_unknown_task_is_noop(self) -> None:
        clear("nonexistent")

    def test_clear_does_not_affect_other_tasks(self) -> None:
        for _ in range(10):
            increment(_TASK)
            increment("other")
        clear(_TASK)
        assert should_block("other")
