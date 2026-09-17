from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cline_hooks.core.state import PluginStateStore

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _SampleState:
    count: int = 0
    label: str = ""


class TestPluginStateStore:
    def test_get_returns_default_when_no_state_file(self, tmp_path: Path) -> None:
        store = PluginStateStore("sample.json", _SampleState, tmp_path / "sample.json")
        assert store.get("task-1") == _SampleState()

    def test_set_then_get_round_trips(self, tmp_path: Path) -> None:
        store = PluginStateStore("sample.json", _SampleState, tmp_path / "sample.json")
        store.set("task-1", _SampleState(count=3, label="x"))
        assert store.get("task-1") == _SampleState(count=3, label="x")

    def test_entries_isolated_per_task(self, tmp_path: Path) -> None:
        store = PluginStateStore("sample.json", _SampleState, tmp_path / "sample.json")
        store.set("task-1", _SampleState(count=3))
        assert store.get("task-2") == _SampleState()

    def test_reset_clears_entry(self, tmp_path: Path) -> None:
        store = PluginStateStore("sample.json", _SampleState, tmp_path / "sample.json")
        store.set("task-1", _SampleState(count=3))
        store.reset("task-1")
        assert store.get("task-1") == _SampleState()

    def test_reset_nonexistent_is_noop(self, tmp_path: Path) -> None:
        store = PluginStateStore("sample.json", _SampleState, tmp_path / "sample.json")
        store.reset("nonexistent")

    def test_reset_does_not_affect_other_tasks(self, tmp_path: Path) -> None:
        store = PluginStateStore("sample.json", _SampleState, tmp_path / "sample.json")
        store.set("task-1", _SampleState(count=1))
        store.set("task-2", _SampleState(count=2))
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

    def test_set_writes_via_tmp_file_then_replace(self, tmp_path: Path) -> None:
        path = tmp_path / "sample.json"
        store = PluginStateStore("sample.json", _SampleState, path)
        store.set("task-1", _SampleState(count=1))
        assert path.exists()
        assert not path.with_suffix(".json.tmp").exists()

    def test_default_path_uses_filename_under_data_dir(self) -> None:
        store = PluginStateStore("sample.json", _SampleState)
        assert store._path.name == "sample.json"
