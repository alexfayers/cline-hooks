from __future__ import annotations

from pathlib import Path

import pytest

from cline_hooks.state import TaskStateStore


@pytest.fixture
def store(tmp_path: Path) -> TaskStateStore:
    return TaskStateStore(tmp_path / "state.json")


class TestTaskStateStore:
    def test_record_and_retrieve_block(self, store: TaskStateStore) -> None:
        store.record_block("task-1", "execute_command", "reason A")
        blocks = store.get_blocks("task-1")
        assert len(blocks) == 1
        assert blocks[0].tool_name == "execute_command"
        assert blocks[0].reason == "reason A"

    def test_multiple_blocks_same_task(self, store: TaskStateStore) -> None:
        store.record_block("task-1", "tool-a", "reason A")
        store.record_block("task-1", "tool-b", "reason B")
        blocks = store.get_blocks("task-1")
        assert len(blocks) == 2

    def test_blocks_isolated_per_task(self, store: TaskStateStore) -> None:
        store.record_block("task-1", "tool", "reason")
        assert store.get_blocks("task-2") == []

    def test_clear_removes_task_blocks(self, store: TaskStateStore) -> None:
        store.record_block("task-1", "tool", "reason")
        store.clear_blocks("task-1")
        assert store.get_blocks("task-1") == []

    def test_clear_nonexistent_task_is_noop(self, store: TaskStateStore) -> None:
        store.clear_blocks("task-999")

    def test_get_empty_when_no_state_file(self, tmp_path: Path) -> None:
        store = TaskStateStore(tmp_path / "nonexistent.json")
        assert store.get_blocks("task-1") == []

    def test_corrupt_state_file_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text("not json")
        store = TaskStateStore(path)
        assert store.get_blocks("task-1") == []

    def test_block_event_has_timestamp(self, store: TaskStateStore) -> None:
        store.record_block("task-1", "tool", "reason")
        block = store.get_blocks("task-1")[0]
        assert block.timestamp
