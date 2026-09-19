from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import TYPE_CHECKING

from cline_hooks.core.state import PluginStateStore

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


@dataclass
class _SampleState:
    count: int = 0
    label: str = ""


def _setter(count: int, label: str = "") -> Callable[[_SampleState], None]:
    def apply(state: _SampleState) -> None:
        state.count = count
        state.label = label

    return apply


class TestPluginStateStore:
    def test_get_returns_default_when_no_state_file(self, tmp_path: Path) -> None:
        store = PluginStateStore("sample.json", _SampleState, tmp_path / "sample.json")
        assert store.get("task-1") == _SampleState()

    def test_update_then_get_round_trips(self, tmp_path: Path) -> None:
        store = PluginStateStore("sample.json", _SampleState, tmp_path / "sample.json")
        store.update("task-1", _setter(3, "x"))
        assert store.get("task-1") == _SampleState(count=3, label="x")

    def test_entries_isolated_per_task(self, tmp_path: Path) -> None:
        store = PluginStateStore("sample.json", _SampleState, tmp_path / "sample.json")
        store.update("task-1", _setter(3))
        assert store.get("task-2") == _SampleState()

    def test_reset_clears_entry(self, tmp_path: Path) -> None:
        store = PluginStateStore("sample.json", _SampleState, tmp_path / "sample.json")
        store.update("task-1", _setter(3))
        store.reset("task-1")
        assert store.get("task-1") == _SampleState()

    def test_reset_nonexistent_is_noop(self, tmp_path: Path) -> None:
        store = PluginStateStore("sample.json", _SampleState, tmp_path / "sample.json")
        store.reset("nonexistent")

    def test_reset_does_not_affect_other_tasks(self, tmp_path: Path) -> None:
        store = PluginStateStore("sample.json", _SampleState, tmp_path / "sample.json")
        store.update("task-1", _setter(1))
        store.update("task-2", _setter(2))
        store.reset("task-1")
        assert store.get("task-2") == _SampleState(count=2)

    def test_corrupt_state_file_returns_default(self, tmp_path: Path) -> None:
        path = tmp_path / "sample.json"
        path.write_text("not json")
        store = PluginStateStore("sample.json", _SampleState, path)
        assert store.get("task-1") == _SampleState()

    def test_malformed_entry_falls_back_to_default(self, tmp_path: Path) -> None:
        path = tmp_path / "sample.json"
        path.write_text('{"task-1": "not-a-dict"}')
        store = PluginStateStore("sample.json", _SampleState, path)
        assert store.get("task-1") == _SampleState()

    def test_unknown_entry_field_falls_back_to_default(self, tmp_path: Path) -> None:
        path = tmp_path / "sample.json"
        path.write_text('{"task-1": {"unknown_field": 1}}')
        store = PluginStateStore("sample.json", _SampleState, path)
        assert store.get("task-1") == _SampleState()

    def test_update_writes_via_tmp_file_then_replace(self, tmp_path: Path) -> None:
        path = tmp_path / "sample.json"
        store = PluginStateStore("sample.json", _SampleState, path)
        store.update("task-1", _setter(1))
        assert path.exists()
        assert not path.with_suffix(".json.tmp").exists()

    def test_default_path_uses_filename_under_data_dir(self) -> None:
        store = PluginStateStore("sample.json", _SampleState)
        assert store._path.name == "sample.json"

    def test_update_concurrent_threads_do_not_lose_updates(self, tmp_path: Path) -> None:
        store = PluginStateStore("sample.json", _SampleState, tmp_path / "sample.json")
        thread_count = 32
        barrier = threading.Barrier(thread_count)

        def increment() -> None:
            def mutate(state: _SampleState) -> int:
                state.count += 1
                return state.count

            barrier.wait()
            store.update("task-1", mutate)

        threads = [threading.Thread(target=increment) for _ in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert store.get("task-1").count == thread_count
