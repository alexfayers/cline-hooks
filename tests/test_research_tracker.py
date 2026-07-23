from __future__ import annotations

from cline_hooks.state.research import (
    DEFAULT_RESEARCH_TOOLS,
    get_research,
    is_research_tool,
    record_research,
    reset,
)

_TASK = "task-1"


class TestIsResearchTool:
    def test_webfetch_is_research(self) -> None:
        assert is_research_tool("WebFetch", frozenset())

    def test_websearch_is_research(self) -> None:
        assert is_research_tool("WebSearch", frozenset())

    def test_read_is_not_research(self) -> None:
        assert not is_research_tool("Read", frozenset())

    def test_bash_is_not_research(self) -> None:
        assert not is_research_tool("Bash", frozenset())

    def test_extra_tool_is_research(self) -> None:
        assert is_research_tool("InternalSearch", frozenset({"InternalSearch"}))

    def test_unknown_extra_tool_is_not_research(self) -> None:
        assert not is_research_tool("InternalSearch", frozenset({"OtherTool"}))

    def test_default_set_contents(self) -> None:
        assert frozenset({"WebFetch", "WebSearch"}) == DEFAULT_RESEARCH_TOOLS


class TestRecordAndGet:
    def test_no_research_initially(self) -> None:
        assert get_research(_TASK) == []

    def test_record_appends(self) -> None:
        record_research(_TASK, "WebFetch", "https://example.com")
        assert get_research(_TASK) == [{"tool": "WebFetch", "detail": "https://example.com"}]

    def test_records_preserve_order(self) -> None:
        record_research(_TASK, "WebSearch", "python entry points")
        record_research(_TASK, "WebFetch", "https://example.com")
        assert get_research(_TASK) == [
            {"tool": "WebSearch", "detail": "python entry points"},
            {"tool": "WebFetch", "detail": "https://example.com"},
        ]

    def test_records_isolated_per_task(self) -> None:
        record_research(_TASK, "WebFetch", "https://example.com")
        assert get_research("other-task") == []


class TestReset:
    def test_reset_clears_research(self) -> None:
        record_research(_TASK, "WebFetch", "https://example.com")
        reset(_TASK)
        assert get_research(_TASK) == []

    def test_reset_does_not_affect_other_tasks(self) -> None:
        record_research(_TASK, "WebFetch", "https://example.com")
        record_research("other-task", "WebSearch", "query")
        reset(_TASK)
        assert get_research("other-task") == [{"tool": "WebSearch", "detail": "query"}]

    def test_reset_nonexistent_is_noop(self) -> None:
        reset("nonexistent")
