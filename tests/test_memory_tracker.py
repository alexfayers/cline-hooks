from __future__ import annotations

import threading

from cline_hooks.state.jsonfile import read_json
import cline_hooks.state.memory as memory_tracker_module
from cline_hooks.state.memory import (
    has_memory_writes,
    is_memory_write,
    record_memory_write,
    reset,
)

_TASK = "task-1"


class TestIsMemoryWrite:
    def test_bare_create_entities(self) -> None:
        assert is_memory_write("create_entities")

    def test_bare_add_observations(self) -> None:
        assert is_memory_write("add_observations")

    def test_bare_set_entity_status(self) -> None:
        assert is_memory_write("set_entity_status")

    def test_bare_create_relations(self) -> None:
        assert is_memory_write("create_relations")

    def test_bare_delete_entity(self) -> None:
        assert is_memory_write("delete_entity")

    def test_read_graph_is_not_write(self) -> None:
        assert not is_memory_write("read_graph")

    def test_frontend_prefixed_name_is_not_matched_raw(self) -> None:
        """Each frontend resolves its own MCP naming before the tracker sees it."""
        assert not is_memory_write("mcp__memory__create_entities")

    def test_search_nodes_is_not_write(self) -> None:
        assert not is_memory_write("search_nodes")

    def test_unrelated_tool_is_not_write(self) -> None:
        assert not is_memory_write("Bash")


class TestRecordAndCheck:
    def test_no_writes_initially(self) -> None:
        assert not has_memory_writes(_TASK)

    def test_record_marks_as_written(self) -> None:
        record_memory_write(_TASK, "create_entities")
        assert has_memory_writes(_TASK)

    def test_multiple_writes_tracked(self) -> None:
        record_memory_write(_TASK, "create_entities")
        record_memory_write(_TASK, "add_observations")
        assert has_memory_writes(_TASK)

    def test_reset_clears_writes(self) -> None:
        record_memory_write(_TASK, "create_entities")
        reset(_TASK)
        assert not has_memory_writes(_TASK)

    def test_reset_does_not_affect_other_tasks(self) -> None:
        record_memory_write(_TASK, "create_entities")
        record_memory_write("other-task", "add_observations")
        reset(_TASK)
        assert has_memory_writes("other-task")

    def test_writes_isolated_per_task(self) -> None:
        record_memory_write(_TASK, "create_entities")
        assert not has_memory_writes("other-task")


class TestConcurrentWrites:
    def test_no_lost_update_under_concurrent_writes(self) -> None:
        thread_count = 32
        barrier = threading.Barrier(thread_count)

        def record(tool_name: str) -> None:
            barrier.wait()
            record_memory_write(_TASK, tool_name)

        tool_names = [f"tool-{i}" for i in range(thread_count)]
        threads = [threading.Thread(target=record, args=(name,)) for name in tool_names]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        data: dict[str, list[str]] = read_json(memory_tracker_module._STATE_PATH, {})
        assert sorted(data[_TASK]) == sorted(tool_names)
