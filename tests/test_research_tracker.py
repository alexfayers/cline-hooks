from __future__ import annotations

import logging

from cline_hooks.core.vocabulary import CanonicalHook
from cline_hooks.plugins.research import (
    ResearchPlugin,
    get_research,
    record_research,
    reset,
)

_TASK = "task-1"


class TestRecordAndGet:
    def test_no_research_initially(self) -> None:
        assert get_research(_TASK) == []

    def test_record_appends(self) -> None:
        record_research(_TASK, "web_fetch", "https://example.com")
        assert get_research(_TASK) == [{"tool": "web_fetch", "detail": "https://example.com"}]

    def test_records_preserve_order(self) -> None:
        record_research(_TASK, "web_search", "python entry points")
        record_research(_TASK, "web_fetch", "https://example.com")
        assert get_research(_TASK) == [
            {"tool": "web_search", "detail": "python entry points"},
            {"tool": "web_fetch", "detail": "https://example.com"},
        ]

    def test_records_isolated_per_task(self) -> None:
        record_research(_TASK, "web_fetch", "https://example.com")
        assert get_research("other-task") == []


class TestReset:
    def test_reset_clears_research(self) -> None:
        record_research(_TASK, "web_fetch", "https://example.com")
        reset(_TASK)
        assert get_research(_TASK) == []

    def test_reset_does_not_affect_other_tasks(self) -> None:
        record_research(_TASK, "web_fetch", "https://example.com")
        record_research("other-task", "web_search", "query")
        reset(_TASK)
        assert get_research("other-task") == [{"tool": "web_search", "detail": "query"}]

    def test_reset_nonexistent_is_noop(self) -> None:
        reset("nonexistent")


class TestStopTrace:
    def test_stop_drains_main_and_subagent_records(self) -> None:
        record_research(_TASK, "web_fetch", "https://example.com")
        record_research(f"{_TASK}:agent-a", "web_search", "query")
        result = ResearchPlugin().on_hook(CanonicalHook.STOP, logger=logging.getLogger("test"), task_id=_TASK)
        assert result is not None
        assert "https://example.com" in result.notes[0]
        assert "query" in result.notes[0]
        assert get_research(_TASK) == []
        assert get_research(f"{_TASK}:agent-a") == []

    def test_subagent_stop_returns_none_and_keeps_records(self) -> None:
        record_research(_TASK, "web_fetch", "https://example.com")
        result = ResearchPlugin().on_hook(CanonicalHook.SUBAGENT_STOP, logger=logging.getLogger("test"), task_id=_TASK)
        assert result is None
        assert get_research(_TASK) == [{"tool": "web_fetch", "detail": "https://example.com"}]
