from __future__ import annotations

from cline_hooks.state.finished import finished_keys, mark_finished, reset

_TASK = "task-1"


class TestFinishedTracker:
    def test_mark_is_idempotent_and_scoped_to_the_task_prefix(self) -> None:
        mark_finished(f"{_TASK}:agent-a")
        mark_finished(f"{_TASK}:agent-a")
        mark_finished("task-10:agent-a")
        assert finished_keys(_TASK) == {f"{_TASK}:agent-a"}

    def test_reset_clears_only_the_task(self) -> None:
        mark_finished(f"{_TASK}:agent-a")
        mark_finished("task-10:agent-a")
        reset(_TASK)
        assert finished_keys(_TASK) == set()
        assert finished_keys("task-10") == {"task-10:agent-a"}
