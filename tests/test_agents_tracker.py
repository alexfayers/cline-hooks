from __future__ import annotations

from cline_hooks.state.agents import (
    agent_use_count,
    has_agent_use,
    is_agent_tool,
    record_agent_use,
    reset,
)

_TASK = "task-1"


class TestIsAgentTool:
    def test_agent(self) -> None:
        assert is_agent_tool("Agent")

    def test_workflow(self) -> None:
        assert is_agent_tool("Workflow")

    def test_new_task(self) -> None:
        assert is_agent_tool("new_task")

    def test_subagent(self) -> None:
        assert is_agent_tool("subagent")

    def test_bash_is_not_agent(self) -> None:
        assert not is_agent_tool("Bash")

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
