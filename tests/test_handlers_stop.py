from __future__ import annotations

import json
from typing import cast
from unittest.mock import patch

import pytest

from cline_hooks.core.models import HookInputStop, StopFields
from cline_hooks.core.protocol import set_protocol
from cline_hooks.frontends.claude_code import ClaudeCodeProtocol
from cline_hooks.frontends.cline import ClineProtocol
from cline_hooks.frontends.kiro import KiroProtocol
from cline_hooks.handlers.stop import _RESEARCH_TRACE_CAP, _format_research_trace, handle_stop
from cline_hooks.state.research import get_research, record_research


def _stop(*, stop_hook_active: bool = False) -> HookInputStop:
    return HookInputStop(
        taskId="task-1",
        workspaceRoots=["/workspace"],
        hookName="Stop",
        stop=StopFields(stopHookActive=stop_hook_active),
    )


def _run(hook: HookInputStop) -> dict[str, object]:
    output: list[str] = []
    with (
        patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
        pytest.raises(SystemExit),
    ):
        handle_stop(hook)
    return cast("dict[str, object]", json.loads(output[0]))


def _run_cc(hook: HookInputStop) -> dict[str, object]:
    output: list[str] = []
    set_protocol(ClaudeCodeProtocol())
    try:
        with (
            patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
            pytest.raises(SystemExit),
        ):
            handle_stop(hook)
    finally:
        set_protocol(ClineProtocol())
    return cast("dict[str, object]", json.loads(output[0]))


class TestFormatResearchTrace:
    def test_empty_records_returns_empty(self) -> None:
        assert _format_research_trace([], "HEADER") == ""

    def test_groups_by_tool(self) -> None:
        records = [
            {"tool": "WebSearch", "detail": "python entry points"},
            {"tool": "WebSearch", "detail": "frozenset union"},
            {"tool": "WebFetch", "detail": "https://example.com"},
        ]
        result = _format_research_trace(records, "HEADER")
        assert '- WebSearch: "python entry points", "frozenset union"' in result
        assert '- WebFetch: "https://example.com"' in result

    def test_dedupes_by_detail(self) -> None:
        records = [
            {"tool": "WebFetch", "detail": "https://example.com"},
            {"tool": "WebFetch", "detail": "https://example.com"},
        ]
        result = _format_research_trace(records, "HEADER")
        assert result.count("https://example.com") == 1

    def test_bare_tool_line_when_no_detail(self) -> None:
        records = [{"tool": "InternalSearch", "detail": ""}]
        result = _format_research_trace(records, "HEADER")
        assert "- InternalSearch" in result
        assert "InternalSearch:" not in result

    def test_truncates_with_explicit_note(self) -> None:
        records = [{"tool": "WebSearch", "detail": f"query {i}"} for i in range(_RESEARCH_TRACE_CAP + 4)]
        result = _format_research_trace(records, "HEADER")
        assert "(+4 more lookups not shown)" in result

    def test_no_truncation_note_when_under_cap(self) -> None:
        records = [{"tool": "WebSearch", "detail": f"query {i}"} for i in range(3)]
        result = _format_research_trace(records, "HEADER")
        assert "more lookups not shown" not in result

    def test_header_included(self) -> None:
        records = [{"tool": "WebFetch", "detail": "https://example.com"}]
        result = _format_research_trace(records, "CUSTOM HEADER TEXT")
        assert result.startswith("CUSTOM HEADER TEXT")


class TestHandleStop:
    def test_research_recorded_forces_block_with_trace(self) -> None:
        record_research("task-1", "WebFetch", "https://example.com/docs")
        result = _run(_stop())
        assert result["cancel"] is True
        assert "https://example.com/docs" in cast("str", result["errorMessage"])

    def test_research_reset_after_block(self) -> None:
        record_research("task-1", "WebFetch", "https://example.com/docs")
        _run(_stop())
        assert get_research("task-1") == []

    def test_no_research_allows(self) -> None:
        result = _run(_stop())
        assert result["cancel"] is False

    def test_stop_hook_active_allows_without_reset(self) -> None:
        record_research("task-1", "WebFetch", "https://example.com/docs")
        result = _run(_stop(stop_hook_active=True))
        assert result["cancel"] is False
        assert get_research("task-1") != []


class TestHandleStopKiro:
    def test_trace_uses_kiro_header(self) -> None:
        record_research("task-1", "WebFetch", "https://example.com/docs")
        output: list[str] = []
        set_protocol(KiroProtocol())
        try:
            with (
                patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
                pytest.raises(SystemExit),
            ):
                handle_stop(_stop())
        finally:
            set_protocol(ClineProtocol())
        result = cast("dict[str, str]", json.loads(output[0]))
        assert "Sources: " in result["reason"]
        assert "No narration" in result["reason"]

    def test_kiro_header_differs_from_claude_code(self) -> None:
        assert KiroProtocol().research_trace_header() != ClaudeCodeProtocol().research_trace_header()


class TestHandleStopClaudeCode:
    def test_research_recorded_emits_additional_context(self) -> None:
        record_research("task-1", "WebFetch", "https://example.com/docs")
        result = _run_cc(_stop())
        hook_output = cast("dict[str, str]", result["hookSpecificOutput"])
        assert hook_output["hookEventName"] == "Stop"
        assert "https://example.com/docs" in hook_output["additionalContext"]

    def test_research_reset_after_feedback(self) -> None:
        record_research("task-1", "WebFetch", "https://example.com/docs")
        _run_cc(_stop())
        assert get_research("task-1") == []

    def test_no_research_allows_empty_stdout(self) -> None:
        output: list[str] = []
        set_protocol(ClaudeCodeProtocol())
        try:
            with (
                patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
                pytest.raises(SystemExit) as exc,
            ):
                handle_stop(_stop())
        finally:
            set_protocol(ClineProtocol())
        assert exc.value.code == 0
        assert output == []

    def test_stop_hook_active_allows_without_reset(self) -> None:
        record_research("task-1", "WebFetch", "https://example.com/docs")
        output: list[str] = []
        set_protocol(ClaudeCodeProtocol())
        try:
            with (
                patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
                pytest.raises(SystemExit) as exc,
            ):
                handle_stop(_stop(stop_hook_active=True))
        finally:
            set_protocol(ClineProtocol())
        assert exc.value.code == 0
        assert get_research("task-1") != []
