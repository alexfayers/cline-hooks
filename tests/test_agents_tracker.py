from __future__ import annotations

import threading

from cline_hooks.state.agents import (
    agent_use_count,
    has_agent_use,
    is_agent_tool,
    record_agent_use,
    reset,
)

_TASK = "task-1"


class TestIsAgentTool:
    def test_spawn_agent(self) -> None:
        assert is_agent_tool("spawn_agent")

    def test_bash_is_not_agent(self) -> None:
        assert not is_agent_tool("execute_command")

    def test_read_is_not_agent(self) -> None:
        assert not is_agent_tool("Read")

    def test_task_create_is_not_agent(self) -> None:
        assert not is_agent_tool("TaskCreate")

    def test_bare_task_is_not_agent(self) -> None:
        assert not is_agent_tool("Task")


class TestRecordAndCheck:
    def test_no_use_initially(self) -> None:
        assert not has_agent_use(_TASK)

    def test_record_marks_as_used(self) -> None:
        record_agent_use(_TASK, "Agent")
        assert has_agent_use(_TASK)

    def test_multiple_uses_tracked(self) -> None:
        record_agent_use(_TASK, "Agent")
        record_agent_use(_TASK, "Workflow")
        assert has_agent_use(_TASK)

    def test_use_isolated_per_task(self) -> None:
        record_agent_use(_TASK, "Agent")
        assert not has_agent_use("other-task")


class TestAgentUseCount:
    def test_zero_initially(self) -> None:
        assert agent_use_count(_TASK) == 0

    def test_counts_each_invocation(self) -> None:
        record_agent_use(_TASK, "Agent")
        record_agent_use(_TASK, "Agent")
        record_agent_use(_TASK, "Workflow")
        assert agent_use_count(_TASK) == 3

    def test_isolated_per_task(self) -> None:
        record_agent_use(_TASK, "Agent")
        record_agent_use("other-task", "Agent")
        record_agent_use("other-task", "Workflow")
        assert agent_use_count(_TASK) == 1
        assert agent_use_count("other-task") == 2


class TestConcurrentRecordAgentUse:
    def test_no_lost_updates_under_concurrent_writes(self) -> None:
        thread_count = 32
        barrier = threading.Barrier(thread_count)

        def record(i: int) -> None:
            barrier.wait()
            record_agent_use(_TASK, f"tool-{i}")

        threads = [threading.Thread(target=record, args=(i,)) for i in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert agent_use_count(_TASK) == thread_count


class TestReset:
    def test_reset_clears_use(self) -> None:
        record_agent_use(_TASK, "Agent")
        reset(_TASK)
        assert not has_agent_use(_TASK)

    def test_reset_does_not_affect_other_tasks(self) -> None:
        record_agent_use(_TASK, "Agent")
        record_agent_use("other-task", "Workflow")
        reset(_TASK)
        assert has_agent_use("other-task")

    def test_reset_nonexistent_is_noop(self) -> None:
        reset("nonexistent")
