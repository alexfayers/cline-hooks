from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import threading

from cline_hooks.state.jsonfile import discard_prefix, read_json, updated_json


class TestReadJson:
    def test_returns_default_when_file_missing(self, tmp_path: Path) -> None:
        assert read_json(tmp_path / "missing.json", {"count": 0}) == {"count": 0}

    def test_returns_default_when_file_corrupt(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text("not json")
        assert read_json(path, {"count": 0}) == {"count": 0}

    def test_returns_parsed_contents(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text(json.dumps({"count": 5}))
        assert read_json(path, {"count": 0}) == {"count": 5}


class TestUpdatedJson:
    def test_yields_default_when_file_missing(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        with updated_json(path, {"count": 0}) as data:
            assert data == {"count": 0}

    def test_persists_mutation_on_exit(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        with updated_json(path, {"count": 0}) as data:
            data["count"] += 1
        assert read_json(path, {"count": -1}) == {"count": 1}

    def test_concurrent_threads_do_not_lose_updates(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        thread_count = 32
        barrier = threading.Barrier(thread_count)

        def increment() -> None:
            barrier.wait()
            with updated_json(path, {"count": 0}) as data:
                data["count"] += 1

        threads = [threading.Thread(target=increment) for _ in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert read_json(path, {"count": -1}) == {"count": thread_count}

    def test_concurrent_processes_do_not_lose_updates(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        process_count = 16
        script = (
            "from pathlib import Path\n"
            "from cline_hooks.state.jsonfile import updated_json\n"
            f"with updated_json(Path({str(path)!r}), {{'count': 0}}) as data:\n"
            "    data['count'] += 1\n"
        )
        src_dir = str(Path(__file__).parent.parent / "src")
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", script],
                env={"PYTHONPATH": src_dir},
            )
            for _ in range(process_count)
        ]
        for process in processes:
            assert process.wait() == 0

        assert read_json(path, {"count": -1}) == {"count": process_count}


class TestDiscardPrefix:
    def test_removes_every_key_with_the_prefix(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text(json.dumps({"task-1:agent-a": 1, "task-1:agent-b": 2, "task-2": 3}))
        discard_prefix(path, "task-1:")
        assert read_json(path, {}) == {"task-2": 3}

    def test_leaves_the_bare_key_untouched(self, tmp_path: Path) -> None:
        path = tmp_path / "state.json"
        path.write_text(json.dumps({"task-1": 1, "task-1:agent-a": 2}))
        discard_prefix(path, "task-1:")
        assert read_json(path, {}) == {"task-1": 1}

    def test_missing_file_is_a_no_op(self, tmp_path: Path) -> None:
        discard_prefix(tmp_path / "missing.json", "task-1:")
        assert not (tmp_path / "missing.json").exists()
