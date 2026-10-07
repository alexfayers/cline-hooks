from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest

from cline_hooks.core.models import HookInputStop, HookInputSubagentStop, StopFields
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.protocol import set_protocol
from cline_hooks.frontends.claude_code import ClaudeCodeProtocol
from cline_hooks.frontends.cline import ClineProtocol
from cline_hooks.frontends.kiro import KiroProtocol
from cline_hooks.handlers.stop import handle_stop, handle_subagent_stop
from cline_hooks.plugins.nudges import _contains_dismissal_signal
from cline_hooks.plugins.research import (
    RESEARCH_TRACE_CAP,
    format_research_trace,
    get_research,
    record_research,
    research_trace_header,
)
from cline_hooks.state.agents import has_agent_use, record_agent_use
from cline_hooks.state.finished import finished_keys
from cline_hooks.state.memory import has_memory_writes, record_memory_write
from cline_hooks.state.skills import is_skill_called, record_skill
from cline_hooks.state.store import TaskStateStore
from cline_hooks.state.workspace import record_workspace, should_note_workspace_change

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


def _subagent_stop(*, agent_id: str = "agent-7", stop_hook_active: bool = False) -> HookInputSubagentStop:
    return HookInputSubagentStop(
        taskId="task-1",
        workspaceRoots=["/workspace"],
        hookName="SubagentStop",
        agentId=agent_id,
        subagentStop=StopFields(stopHookActive=stop_hook_active),
    )


def _run(hook: HookInputStop) -> dict[str, object]:
    output: list[str] = []
    with (
        patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
        pytest.raises(SystemExit),
    ):
        handle_stop(hook)
    return cast("dict[str, object]", json.loads(output[0]))


def _run_subagent(hook: HookInputSubagentStop) -> dict[str, object]:
    output: list[str] = []
    with (
        patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
        pytest.raises(SystemExit),
    ):
        handle_subagent_stop(hook)
    return cast("dict[str, object]", json.loads(output[0]))


def _run_raw(hook: HookInputStop) -> str:
    output: list[str] = []
    with (
        patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
        pytest.raises(SystemExit),
    ):
        handle_stop(hook)
    return output[0]


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


def _seed_state(key: str) -> None:
    record_skill(key, "some-skill")
    record_memory_write(key, "create_entities")
    record_agent_use(key, "Agent")
    record_workspace(key, ["/workspace"])
    TaskStateStore().record_block(key, "Bash", "reason")


def _has_state(key: str) -> bool:
    return (
        is_skill_called(key, "some-skill")
        and has_memory_writes(key)
        and has_agent_use(key)
        and should_note_workspace_change(key, ["/other"])
        and bool(TaskStateStore().get_blocks(key))
    )


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

    def test_subagent_lookups_get_separate_labelled_line(self) -> None:
        records = [
            {"tool": "web_fetch", "detail": "https://example.com"},
            {"tool": "web_fetch", "detail": "https://example.org", "agent": "Explore/agent-a"},
            {"tool": "InternalSearch", "detail": "", "agent": "Explore/agent-a"},
        ]
        result = format_research_trace(records, "HEADER")
        assert '- web_fetch: "https://example.com"' in result
        assert '- web_fetch via Explore/agent-a: "https://example.org"' in result
        assert "- InternalSearch via Explore/agent-a" in result

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


class TestHandleSubagentStop:
    def test_dispatches_with_the_subagent_state_key(self) -> None:
        captured: list[dict[str, object]] = []

        def _fake_collect(_plugins: object, _hook_name: str, **kwargs: object) -> HookResult:
            captured.append(kwargs)
            return HookResult()

        with (
            patch("cline_hooks.handlers.stop.collect_hook_results", side_effect=_fake_collect),
            patch("builtins.print"),
            pytest.raises(SystemExit),
        ):
            handle_subagent_stop(_subagent_stop())
        assert captured
        assert captured[0].get("task_id") == "task-1:agent-7"
        assert captured[0].get("agent_id") == "agent-7"

    def test_stop_hook_active_allows_without_dispatch(self) -> None:
        with (
            patch("cline_hooks.handlers.stop.collect_hook_results") as mock_collect,
            patch("builtins.print"),
            pytest.raises(SystemExit) as exc,
        ):
            handle_subagent_stop(_subagent_stop(stop_hook_active=True))
        mock_collect.assert_not_called()
        assert exc.value.code == 0

    def test_research_recorded_for_the_subagent_is_not_traced_and_is_kept(self) -> None:
        record_research("task-1:agent-7", "WebFetch", "https://example.com/subagent-docs")
        result = _run_subagent(_subagent_stop())
        assert result == {"cancel": False}
        assert get_research("task-1:agent-7") == [{"tool": "WebFetch", "detail": "https://example.com/subagent-docs"}]

    def test_no_research_for_an_internal_agent_with_empty_agent_type_allows(self) -> None:
        hook = _subagent_stop(agent_id="internal-agent-1")
        hook.agentType = ""
        result = _run_subagent(hook)
        assert result == {"cancel": False}

    def test_main_stop_trace_includes_main_and_subagent_lookups_then_clears_both(self) -> None:
        record_research("task-1", "WebFetch", "https://example.com/main-docs")
        record_research("task-1:agent-7", "WebFetch", "https://example.com/subagent-docs")
        _run_subagent(_subagent_stop())
        message = cast("str", _run(_stop())["errorMessage"])
        assert "https://example.com/main-docs" in message
        assert "https://example.com/subagent-docs" in message
        assert get_research("task-1") == []
        assert get_research("task-1:agent-7") == []

    @pytest.mark.parametrize("stop_hook_active", [False, True])
    def test_subagent_stop_clears_only_the_subagents_state(self, stop_hook_active: bool) -> None:
        for key in ("task-1", "task-1:agent-7"):
            _seed_state(key)
        _run_subagent(_subagent_stop(stop_hook_active=stop_hook_active))
        assert _has_state("task-1")
        assert not _has_state("task-1:agent-7")

    def test_subagent_stop_keeps_the_subagents_state_when_a_plugin_note_gives_feedback(self) -> None:
        class _NotingPlugin(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
                return HookResult(notes=["PLUGIN NOTE"])

        for key in ("task-1", "task-1:agent-7"):
            _seed_state(key)
        with patch("cline_hooks.handlers.stop.load_plugins", return_value=[_NotingPlugin()]):
            result = _run_subagent(_subagent_stop())
        assert "PLUGIN NOTE" in cast("str", result["errorMessage"])
        assert _has_state("task-1")
        assert _has_state("task-1:agent-7")

    def test_subagent_stop_without_agent_id_clears_nothing(self) -> None:
        _seed_state("task-1")
        _run_subagent(_subagent_stop(agent_id=""))
        assert _has_state("task-1")

    @pytest.mark.parametrize("stop_hook_active", [False, True])
    def test_subagent_stop_marks_the_subagent_finished(self, stop_hook_active: bool) -> None:
        _run_subagent(_subagent_stop(stop_hook_active=stop_hook_active))
        assert finished_keys("task-1") == {"task-1:agent-7"}


class TestHandleSubagentStopClaudeCode:
    def test_research_recorded_for_that_agent_allows_empty_stdout(self) -> None:
        record_research("task-1:agent-7", "WebFetch", "https://example.com/subagent-docs")
        output: list[str] = []
        set_protocol(ClaudeCodeProtocol("SubagentStop"))
        try:
            with (
                patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
                pytest.raises(SystemExit) as exc,
            ):
                handle_subagent_stop(_subagent_stop())
        finally:
            set_protocol(ClineProtocol())
        assert exc.value.code == 0
        assert output == []


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

    def test_subagent_task_id_is_the_per_agent_state_key(self) -> None:
        captured: list[dict[str, object]] = []

        def _fake_collect(_plugins: object, _hook_name: str, **kwargs: object) -> HookResult:
            captured.append(kwargs)
            return HookResult()

        hook = _stop()
        hook.agentId = "agent-7"
        with (
            patch("cline_hooks.handlers.stop.collect_hook_results", side_effect=_fake_collect),
            patch("builtins.print"),
            pytest.raises(SystemExit),
        ):
            handle_stop(hook)
        assert captured
        assert captured[0].get("task_id") == "task-1:agent-7"
        assert captured[0].get("agent_id") == "agent-7"
