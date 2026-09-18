from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import threading
from typing import cast

from cline_hooks.state.jsonfile import read_json
import cline_hooks.state.retrospective as module
from cline_hooks.state.retrospective import get_count, record_session, reset


class TestRecordAndCount:
    def test_count_is_zero_initially(self) -> None:
        assert get_count() == 0

    def test_first_session_increments_to_one(self) -> None:
        assert record_session("t1") == 1
        assert get_count() == 1

    def test_repeated_session_is_not_counted_again(self) -> None:
        assert record_session("t1") == 1
        assert record_session("t1") is None
        assert get_count() == 1

    def test_distinct_sessions_increment(self) -> None:
        assert record_session("t1") == 1
        assert record_session("t2") == 2
        assert get_count() == 2

    def test_falsy_task_id_is_not_counted(self) -> None:
        assert record_session("") is None
        assert get_count() == 0


class TestReset:
    def test_reset_zeroes_count(self) -> None:
        record_session("t1")
        record_session("t2")
        reset()
        assert get_count() == 0

    def test_reset_clears_session_guard(self) -> None:
        record_session("t1")
        reset()
        assert record_session("t1") == 1


class TestBounds:
    def test_guard_is_capped_to_max_tracked_sessions(self) -> None:
        for i in range(module._MAX_TRACKED_SESSIONS + 10):
            record_session(f"t{i}")
        data = read_json(module._STATE_PATH, module._default())
        counted = cast("list[str]", data["counted_sessions"])
        assert len(counted) == module._MAX_TRACKED_SESSIONS

    def test_count_keeps_growing_past_cap(self) -> None:
        for i in range(module._MAX_TRACKED_SESSIONS + 10):
            record_session(f"t{i}")
        assert get_count() == module._MAX_TRACKED_SESSIONS + 10


class TestPersistence:
    def test_corrupt_state_is_treated_as_fresh(self) -> None:
        module._STATE_PATH.write_text("not json")
        assert get_count() == 0
        assert record_session("t1") == 1

    def test_count_persists_across_reads(self) -> None:
        record_session("t1")
        assert get_count() == 1
        assert get_count() == 1


class TestConcurrency:
    def test_concurrent_threads_do_not_lose_updates(self) -> None:
        thread_count = 32
        barrier = threading.Barrier(thread_count)

        def record(session_id: str) -> None:
            barrier.wait()
            record_session(session_id)

        threads = [threading.Thread(target=record, args=(f"session-{i}",)) for i in range(thread_count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert get_count() == thread_count

    def test_concurrent_processes_do_not_lose_updates(self, tmp_path: Path) -> None:
        state_path = tmp_path / "cross-process-retrospective-state.json"
        process_count = 16
        src_dir = str(Path(__file__).parent.parent / "src")
        processes = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    (
                        "import sys, pathlib\n"
                        "import cline_hooks.state.retrospective as m\n"
                        "m._STATE_PATH = pathlib.Path(sys.argv[1])\n"
                        "m.record_session(sys.argv[2])\n"
                    ),
                    str(state_path),
                    f"session-{i}",
                ],
                env={"PYTHONPATH": src_dir},
            )
            for i in range(process_count)
        ]
        for process in processes:
            assert process.wait() == 0

        module._STATE_PATH = state_path
        assert get_count() == process_count
