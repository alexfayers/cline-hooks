from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from cline_hooks.core.models import HookInputStop, StopFields
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.protocol import get_protocol, set_protocol
from cline_hooks.core.response import render
from cline_hooks.frontends.claude_code import ClaudeCodeProtocol
from cline_hooks.frontends.cline import ClineProtocol
from cline_hooks.frontends.kiro import KiroProtocol
from cline_hooks.handlers.stop import handle_stop
from cline_hooks.plugins.nudges import _contains_dismissal_signal
from cline_hooks.plugins.research import (
    RESEARCH_TRACE_CAP,
    format_research_trace,
    get_research,
    record_research,
    research_trace_header,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.conftest import StubTranscript

    StubTranscriptT = Callable[..., StubTranscript]


def _stop(*, stop_hook_active: bool = False, transcript_path: str = "") -> HookInputStop:
    return HookInputStop(
        taskId="task-1",
        workspaceRoots=["/workspace"],
        hookName="Stop",
        transcriptPath=transcript_path,
        stop=StopFields(stopHookActive=stop_hook_active),
    )


def _run(hook: HookInputStop) -> dict[str, object]:
    outcome = handle_stop(hook)
    assert outcome is not None
    response = render(outcome, get_protocol())
    return cast("dict[str, object]", json.loads(response.stdout))


def _run_raw(hook: HookInputStop) -> str:
    outcome = handle_stop(hook)
    assert outcome is not None
    return render(outcome, get_protocol()).stdout


def _run_cc(hook: HookInputStop) -> dict[str, object]:
    set_protocol(ClaudeCodeProtocol())
    try:
        outcome = handle_stop(hook)
        assert outcome is not None
        response = render(outcome, get_protocol())
    finally:
        set_protocol(ClineProtocol())
    return cast("dict[str, object]", json.loads(response.stdout))


class TestFormatResearchTrace:
    def test_empty_records_returns_empty(self) -> None:
        assert format_research_trace([], "HEADER") == ""

    def test_groups_by_tool(self) -> None:
        records = [
            {"tool": "WebSearch", "detail": "python entry points"},
            {"tool": "WebSearch", "detail": "frozenset union"},
            {"tool": "WebFetch", "detail": "https://example.com"},
        ]
        result = format_research_trace(records, "HEADER")
        assert '- WebSearch: "python entry points", "frozenset union"' in result
        assert '- WebFetch: "https://example.com"' in result

    def test_dedupes_by_detail(self) -> None:
        records = [
            {"tool": "WebFetch", "detail": "https://example.com"},
            {"tool": "WebFetch", "detail": "https://example.com"},
        ]
        result = format_research_trace(records, "HEADER")
        assert result.count("https://example.com") == 1

    def test_bare_tool_line_when_no_detail(self) -> None:
        records = [{"tool": "InternalSearch", "detail": ""}]
        result = format_research_trace(records, "HEADER")
        assert "- InternalSearch" in result
        assert "InternalSearch:" not in result

    def test_truncates_with_explicit_note(self) -> None:
        records = [{"tool": "WebSearch", "detail": f"query {i}"} for i in range(RESEARCH_TRACE_CAP + 4)]
        result = format_research_trace(records, "HEADER")
        assert "(+4 more lookups not shown)" in result

    def test_no_truncation_note_when_under_cap(self) -> None:
        records = [{"tool": "WebSearch", "detail": f"query {i}"} for i in range(3)]
        result = format_research_trace(records, "HEADER")
        assert "more lookups not shown" not in result

    def test_header_included(self) -> None:
        records = [{"tool": "WebFetch", "detail": "https://example.com"}]
        result = format_research_trace(records, "CUSTOM HEADER TEXT")
        assert result.startswith("CUSTOM HEADER TEXT")


class TestContainsDismissalSignal:
    def test_matches_pre_existing_error(self) -> None:
        assert _contains_dismissal_signal("This is a pre-existing error unrelated to my change.")

    def test_matches_preexisting_issue_no_hyphen(self) -> None:
        assert _contains_dismissal_signal("That's a preexisting issue in the codebase.")

    def test_matches_error_was_pre_existing(self) -> None:
        assert _contains_dismissal_signal("The error was pre-existing before I started.")

    def test_matches_out_of_scope(self) -> None:
        assert _contains_dismissal_signal("Fixing that is out of scope for this fix.")

    def test_no_match_on_clean_message(self) -> None:
        assert not _contains_dismissal_signal("I fixed the bug and all tests pass now.")

    def test_case_insensitive(self) -> None:
        assert _contains_dismissal_signal("PRE-EXISTING ISSUE, not touching it.")


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

    def test_dismissal_signal_forces_block_with_nudge(self, stub_transcript: StubTranscriptT) -> None:
        stub_transcript(text="This is a pre-existing issue.")
        result = _run(_stop(transcript_path="session.jsonl"))
        assert result["cancel"] is True
        assert "DISMISSED ISSUE DETECTED" in cast("str", result["errorMessage"])

    def test_dismissal_signal_and_research_both_included(self, stub_transcript: StubTranscriptT) -> None:
        stub_transcript(text="This is a pre-existing issue.")
        record_research("task-1", "WebFetch", "https://example.com/docs")
        result = _run(_stop(transcript_path="session.jsonl"))
        message = cast("str", result["errorMessage"])
        assert "DISMISSED ISSUE DETECTED" in message
        assert "https://example.com/docs" in message

    def test_no_dismissal_signal_no_research_allows(self, stub_transcript: StubTranscriptT) -> None:
        stub_transcript(text="Everything looks good.")
        result = _run(_stop(transcript_path="session.jsonl"))
        assert result["cancel"] is False

    def test_dismissal_signal_anywhere_in_turn_text_detected(self, stub_transcript: StubTranscriptT) -> None:
        stub_transcript(text="This is a pre-existing issue, moving on.\nAll done, tests pass.")
        result = _run(_stop(transcript_path="session.jsonl"))
        assert result["cancel"] is True
        assert "DISMISSED ISSUE DETECTED" in cast("str", result["errorMessage"])

    def test_stop_hook_active_skips_dismissal_check(self, stub_transcript: StubTranscriptT) -> None:
        stub_transcript(text="This is a pre-existing issue.")
        result = _run(_stop(stop_hook_active=True, transcript_path="session.jsonl"))
        assert result["cancel"] is False

    def test_no_transcript_path_allows(self) -> None:
        result = _run(_stop())
        assert result["cancel"] is False


class TestHandleStopKiro:
    def test_trace_uses_kiro_header(self) -> None:
        record_research("task-1", "WebFetch", "https://example.com/docs")
        set_protocol(KiroProtocol())
        try:
            outcome = handle_stop(_stop())
            assert outcome is not None
            response = render(outcome, get_protocol())
        finally:
            set_protocol(ClineProtocol())
        result = cast("dict[str, str]", json.loads(response.stdout))
        assert "Sources: " in result["reason"]
        assert "No narration" in result["reason"]

    def test_a_frontend_that_declares_nothing_gets_the_neutral_header(self) -> None:
        """The base header assumes nothing about where hook output surfaces."""
        set_protocol(ClineProtocol())
        try:
            header = research_trace_header()
        finally:
            set_protocol(ClineProtocol())
        assert "MUST cite the lookups" in header
        assert "raw output" not in header

    def test_kiro_header_differs_from_the_neutral_default(self) -> None:
        set_protocol(KiroProtocol())
        try:
            kiro_header = research_trace_header()
        finally:
            set_protocol(ClineProtocol())
        cline_header = research_trace_header()
        assert kiro_header != cline_header


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
        set_protocol(ClaudeCodeProtocol())
        try:
            outcome = handle_stop(_stop())
            assert outcome is not None
            response = render(outcome, get_protocol())
        finally:
            set_protocol(ClineProtocol())
        assert response.exit_code == 0
        assert response.stdout == ""

    def test_stop_hook_active_allows_without_reset(self) -> None:
        record_research("task-1", "WebFetch", "https://example.com/docs")
        set_protocol(ClaudeCodeProtocol())
        try:
            outcome = handle_stop(_stop(stop_hook_active=True))
            assert outcome is not None
            response = render(outcome, get_protocol())
        finally:
            set_protocol(ClineProtocol())
        assert response.exit_code == 0
        assert get_research("task-1") != []


class TestHandleStopPluginDispatch:
    def test_plugin_note_appears_when_handler_has_no_notes_of_its_own(self) -> None:
        class _NotingPlugin(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
                return HookResult(notes=["PLUGIN NOTE"])

        with patch(
            "cline_hooks.handlers.stop.load_plugins",
            return_value=[_NotingPlugin()],
        ):
            result = _run(_stop())
        assert result["cancel"] is True
        assert "PLUGIN NOTE" in cast("str", result["errorMessage"])

    def test_plugin_block_string_surfaces_as_feedback_text(self) -> None:
        class _BlockingPlugin(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
                return HookResult(block="plugin block text")

        with patch(
            "cline_hooks.handlers.stop.load_plugins",
            return_value=[_BlockingPlugin()],
        ):
            result = _run(_stop())
        assert result["cancel"] is True
        assert "plugin block text" in cast("str", result["errorMessage"])

    def test_plugin_returning_nothing_leaves_output_byte_identical(self) -> None:
        class _QuietPlugin(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
                return None

        baseline = _run_raw(_stop())

        with patch(
            "cline_hooks.handlers.stop.load_plugins",
            return_value=[_QuietPlugin()],
        ):
            with_plugin = _run_raw(_stop())
        assert with_plugin == baseline
