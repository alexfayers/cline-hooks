from __future__ import annotations

from typing import cast

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
        counted = cast("list[str]", module._read()["counted_sessions"])
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
