from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import patch

from cline_hooks.core.models import HookInput, HookInputPostToolUse
from cline_hooks.core.plugin import HookResult, HooksPlugin, ToolingNote
from cline_hooks.core.protocol import RawPayload, get_protocol
from cline_hooks.core.response import render
from cline_hooks.frontends.claude_code import ClaudeCodeProtocol
from cline_hooks.frontends.cline import ClineProtocol
from cline_hooks.handlers.post_tool_use import _record_tool_use, handle_post_tool_use
from cline_hooks.plugins.build_tools import BuildToolsPlugin
from cline_hooks.plugins.context_usage import context_note
from cline_hooks.plugins.nudges import _RETRO_THRESHOLD, NudgesPlugin
from cline_hooks.plugins.persistence import PersistencePlugin
from cline_hooks.plugins.plan_handoff import consume_plan_nudge, record_plan_exit
from cline_hooks.plugins.research import (
    ResearchPlugin,
    extract_research_detail,
    get_all_research_detail_extractors,
    get_all_research_tool_names,
    get_research,
)
from cline_hooks.state.memory import record_memory_write
from cline_hooks.state.retrospective import get_count, record_session
from cline_hooks.state.workspace import record_workspace

if TYPE_CHECKING:
    from collections.abc import Callable
    import logging
    from pathlib import Path

    from tests.conftest import StubTranscript

    StubTranscriptT = Callable[..., StubTranscript]


def parse_data(raw: str) -> HookInput:
    return ClineProtocol().parse(RawPayload.from_stdin(raw))


_BASE = {
    "clineVersion": "1.0",
    "timestamp": "2024-01-01T00:00:00Z",
    "taskId": "task-1",
    "userId": "user-1",
    "workspaceRoots": ["/workspace"],
    "hookName": "PostToolUse",
}


def _make_hook(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]
    tool_name: str,
    success: bool = True,
    result: str | None = None,
    parameters: dict[str, object] | None = None,
    workspace_roots: list[str] | None = None,
    transcript_path: str | None = None,
) -> HookInputPostToolUse:
    data = {
        **_BASE,
        "workspaceRoots": workspace_roots if workspace_roots is not None else ["/workspace"],
        "postToolUse": {
            "toolName": tool_name,
            "parameters": parameters or {},
            "success": success,
            "executionTimeMs": 10,
            "result": result,
        },
    }
    if transcript_path is not None:
        data["transcriptPath"] = transcript_path
    hook = parse_data(json.dumps(data))
    assert isinstance(hook, HookInputPostToolUse)
    return hook


def _run(hook: HookInputPostToolUse) -> dict[str, object] | None:
    outcome = handle_post_tool_use(hook)
    if outcome is None or outcome.message is None:
        return None
    response = render(outcome, get_protocol())
    if not response.stdout:
        return None
    return cast("dict[str, object]", json.loads(response.stdout))


class TestHandlePostToolUse:
    def test_failed_tool_fires_persist_reminder(self) -> None:
        hook = _make_hook("replace_in_file", success=False)
        result = _run(hook)
        assert result is not None
        context = str(result.get("contextModification", ""))
        assert "failed" in context.lower()
        assert "persist" in context.lower()

    def test_build_failed_triggers_alert(self) -> None:
        hook = _make_hook("execute_command", result="BUILD FAILED: something went wrong")
        result = _run(hook)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "FAILED" in context


class TestPostToolUseContextNudge:
    def test_info_note_fires_on_tool_use(self, stub_transcript: StubTranscriptT) -> None:
        stub_transcript(tokens=150_000)
        hook = _make_hook("Read", transcript_path="session.jsonl")
        result = _run(hook)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "CONTEXT STATUS" in context
        assert "150,000" in context

    def test_no_nudge_when_no_transcript_path(self) -> None:
        hook = _make_hook("Read")
        result = _run(hook)
        assert result is None

    def test_no_nudge_when_token_count_unavailable(self, stub_transcript: StubTranscriptT) -> None:
        stub_transcript(tokens=None)
        hook = _make_hook("Read", transcript_path="session.jsonl")
        result = _run(hook)
        assert result is None

    def test_band_already_claimed_by_user_prompt_submit_does_not_refire(self, stub_transcript: StubTranscriptT) -> None:
        stub_transcript(tokens=155_000)
        context_note("task-1", 150_000)
        hook = _make_hook("Read", transcript_path="session.jsonl")
        result = _run(hook)
        assert result is None


class TestForwardsAgentType:
    def test_agent_type_forwarded_to_plugins(self) -> None:
        captured: list[dict[str, object]] = []

        def _fake_collect(_plugins: object, _hook_name: str, **kwargs: object) -> object:
            captured.append(kwargs)
            from cline_hooks.core.plugin import HookResult

            return HookResult()

        hook = _make_hook("read_file", parameters={"path": "/x.py"})
        hook.agentType = "Explore"
        with (
            patch(
                "cline_hooks.handlers.post_tool_use.collect_hook_results",
                side_effect=_fake_collect,
            ),
            patch("builtins.print"),
        ):
            handle_post_tool_use(hook)
        assert captured
        assert captured[0].get("agent_type") == "Explore"


class TestSkillDetectionViaRead:
    def test_skill_md_read_records_skill(self) -> None:
        hook = _make_hook(
            "read_file",
            parameters={"path": "/home/user/.kiro/skills/git-usage/SKILL.md"},
        )
        with patch("cline_hooks.plugins.tracking.record_skill") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "git-usage")

    def test_non_skill_read_does_not_record(self) -> None:
        hook = _make_hook("read_file", parameters={"path": "/home/user/project/README.md"})
        with patch("cline_hooks.plugins.tracking.record_skill") as mock_record:
            _run(hook)
        mock_record.assert_not_called()

    def test_skill_md_in_nested_path(self) -> None:
        hook = _make_hook(
            "read_file",
            parameters={"path": "/deep/nested/skills/pre-implementation/SKILL.md"},
        )
        with patch("cline_hooks.plugins.tracking.record_skill") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "pre-implementation")

    def test_empty_path_does_not_record(self) -> None:
        hook = _make_hook("read_file", parameters={})
        with patch("cline_hooks.plugins.tracking.record_skill") as mock_record:
            _run(hook)
        mock_record.assert_not_called()

    def test_claude_code_read_skill_detected(self) -> None:
        hook = ClaudeCodeProtocol().parse(
            RawPayload.from_stdin(
                json.dumps({
                    "hook_event_name": "PostToolUse",
                    "session_id": "task-1",
                    "cwd": "/workspace",
                    "tool_name": "Read",
                    "tool_input": {"file_path": "/Users/me/.claude/skills/git-usage/SKILL.md"},
                })
            )
        )
        assert isinstance(hook, HookInputPostToolUse)
        with patch("cline_hooks.plugins.tracking.record_skill") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "git-usage")


class TestSkillDetectionViaShellCommand:
    def test_cat_skill_md_records_skill(self) -> None:
        hook = _make_hook(
            "execute_command",
            parameters={"command": "cat /Users/me/.codex/skills/git-usage/SKILL.md"},
        )
        with patch("cline_hooks.plugins.tracking.record_skill") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "git-usage")

    def test_sed_skill_md_records_skill(self) -> None:
        hook = _make_hook(
            "execute_command",
            parameters={"command": "sed -n '1,260p' /a/b/skills/pre-implementation/SKILL.md"},
        )
        with patch("cline_hooks.plugins.tracking.record_skill") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "pre-implementation")

    def test_execute_command_skill_md_records_skill(self) -> None:
        hook = _make_hook(
            "execute_command",
            parameters={"command": "less /deep/skills/cr/SKILL.md"},
        )
        with patch("cline_hooks.plugins.tracking.record_skill") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "cr")

    def test_git_command_does_not_record_skill(self) -> None:
        hook = _make_hook("Bash", parameters={"command": "git -P status --short"})
        with patch("cline_hooks.plugins.tracking.record_skill") as mock_record:
            _run(hook)
        mock_record.assert_not_called()

    def test_bare_skill_md_reference_does_not_record(self) -> None:
        hook = _make_hook("Bash", parameters={"command": "find . -name SKILL.md"})
        with patch("cline_hooks.plugins.tracking.record_skill") as mock_record:
            _run(hook)
        mock_record.assert_not_called()


class TestAgentUseRecording:
    def test_spawn_agent_records_use(self) -> None:
        hook = _make_hook("spawn_agent", parameters={"description": "research"})
        with patch("cline_hooks.plugins.tracking.record_agent_use") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "spawn_agent")

    def test_non_agent_tool_does_not_record(self) -> None:
        hook = _make_hook("execute_command", parameters={"command": "echo hi"})
        with patch("cline_hooks.plugins.tracking.record_agent_use") as mock_record:
            _run(hook)
        mock_record.assert_not_called()

    def test_agent_tool_does_not_record_skill_or_memory(self) -> None:
        hook = _make_hook("spawn_agent", parameters={"description": "research"})
        with (
            patch("cline_hooks.plugins.tracking.record_skill") as mock_skill,
            patch("cline_hooks.plugins.tracking.record_memory_write") as mock_memory,
        ):
            _run(hook)
        mock_skill.assert_not_called()
        mock_memory.assert_not_called()


class TestPlanExitRecording:
    def test_exit_plan_mode_records_plan_exit(self) -> None:
        _run(_make_hook("exit_plan_mode"))
        assert consume_plan_nudge("task-1") is True

    def test_non_plan_tool_does_not_record(self) -> None:
        _run(_make_hook("read_file", parameters={"path": "/x.py"}))
        assert consume_plan_nudge("task-1") is False


class TestPlanHandoffNudgeFromPostToolUse:
    def test_plan_nudge_fires_after_plan_exit(self) -> None:
        record_plan_exit("task-1")
        result = _run(_make_hook("Read", parameters={"file_path": "/x.py"}))
        assert result is not None
        assert "PLAN COMPLETE" in cast("str", result.get("contextModification", ""))

    def test_nudge_does_not_self_consume_on_the_plan_exit_call(self) -> None:
        exit_result = _run(_make_hook("exit_plan_mode"))
        if exit_result is not None:
            assert "PLAN COMPLETE" not in cast("str", exit_result.get("contextModification", ""))

        next_result = _run(_make_hook("Read", parameters={"file_path": "/x.py"}))
        assert next_result is not None
        assert "PLAN COMPLETE" in cast("str", next_result.get("contextModification", ""))

        third_result = _run(_make_hook("Read", parameters={"file_path": "/y.py"}))
        if third_result is not None:
            assert "PLAN COMPLETE" not in cast("str", third_result.get("contextModification", ""))


class TestGetAllResearchToolNames:
    def test_no_plugins_returns_empty(self) -> None:
        assert get_all_research_tool_names([]) == frozenset()

    def test_includes_default_plugin_tools(self) -> None:
        assert get_all_research_tool_names([ResearchPlugin()]) == frozenset({"web_fetch", "web_search"})

    def test_union_with_plugin_names(self) -> None:
        class _ExtraToolsPlugin(HooksPlugin):
            def get_research_tool_names(self) -> frozenset[str]:
                return frozenset({"InternalSearch", "InternalCodeSearch"})

        result = get_all_research_tool_names([ResearchPlugin(), _ExtraToolsPlugin()])
        assert result == frozenset({"web_fetch", "web_search", "InternalSearch", "InternalCodeSearch"})


class TestGetAllResearchDetailExtractors:
    def test_empty_with_no_plugins(self) -> None:
        assert get_all_research_detail_extractors([]) == {}

    def test_merges_from_plugin(self) -> None:
        class ExtractorPlugin(HooksPlugin):
            def get_research_detail_extractors(
                self,
            ) -> dict[str, Callable[[dict[str, Any]], str]]:
                return {"InternalSearch": lambda p: p.get("query", "")}

        result = get_all_research_detail_extractors([ExtractorPlugin()])
        assert set(result) == {"InternalSearch"}

    def test_last_plugin_wins_on_collision(self) -> None:
        class PluginA(HooksPlugin):
            def get_research_detail_extractors(
                self,
            ) -> dict[str, Callable[[dict[str, Any]], str]]:
                return {"X": lambda _p: "a"}

        class PluginB(HooksPlugin):
            def get_research_detail_extractors(
                self,
            ) -> dict[str, Callable[[dict[str, Any]], str]]:
                return {"X": lambda _p: "b"}

        result = get_all_research_detail_extractors([PluginA(), PluginB()])
        assert result["X"]({}) == "b"


class TestExtractResearchDetail:
    def test_extractor_used_when_present(self) -> None:
        assert extract_research_detail("X", {"k": "v"}, {"X": lambda p: p["k"]}) == "v"  # ruff: ignore[reimplemented-operator]

    def test_webfetch_fallback(self) -> None:
        assert extract_research_detail("web_fetch", {"url": "u"}, {}) == "u"

    def test_websearch_fallback(self) -> None:
        assert extract_research_detail("web_search", {"query": "q"}, {}) == "q"

    def test_unknown_tool_returns_empty(self) -> None:
        assert extract_research_detail("Unknown", {"url": "u"}, {}) == ""

    def test_extractor_raises_returns_empty(self) -> None:
        def _boom(_p: dict[str, Any]) -> str:
            msg = "boom"
            raise RuntimeError(msg)

        assert extract_research_detail("X", {}, {"X": _boom}) == ""

    def test_extractor_returns_none_coerced_empty(self) -> None:
        def _none(_p: dict[str, Any]) -> str:
            return cast("str", None)

        assert extract_research_detail("X", {}, {"X": _none}) == ""


class TestResearchRecording:
    def test_webfetch_records_url(self) -> None:
        _run(_make_hook("web_fetch", parameters={"url": "https://example.com/docs"}))
        assert get_research("task-1") == [{"tool": "web_fetch", "detail": "https://example.com/docs"}]

    def test_websearch_records_query(self) -> None:
        _run(_make_hook("web_search", parameters={"query": "python entry points"}))
        assert get_research("task-1") == [{"tool": "web_search", "detail": "python entry points"}]

    def test_non_research_tool_records_nothing(self) -> None:
        _run(_make_hook("read_file", parameters={"path": "/x.py"}))
        assert get_research("task-1") == []

    def test_failed_research_tool_records_nothing(self) -> None:
        _run(_make_hook("web_fetch", success=False, parameters={"url": "https://example.com"}))
        assert get_research("task-1") == []


class TestClaudeCodeMcpResearchIntegration:
    def test_prefixed_mcp_tool_records_research_via_plugin(self) -> None:
        """A Claude Code mcp__ name reaches the handler already normalised."""

        class _ReadInternalWebsitesPlugin(HooksPlugin):
            def get_research_tool_names(self) -> frozenset[str]:
                return frozenset({"ReadInternalWebsites"})

            def get_research_detail_extractors(
                self,
            ) -> dict[str, Callable[[dict[str, Any]], str]]:
                return {"ReadInternalWebsites": lambda p: p.get("inputs", [""])[0]}

        payload = {
            "hook_event_name": "PostToolUse",
            "session_id": "task-1",
            "cwd": "/workspace",
            "tool_name": "mcp__builder-mcp__ReadInternalWebsites",
            "tool_input": {"inputs": ["https://example.com/x"]},
            "tool_response": {"success": True},
        }
        hook = ClaudeCodeProtocol().parse(RawPayload(raw=json.dumps(payload), data=payload, env={}))
        assert isinstance(hook, HookInputPostToolUse)
        assert hook.postToolUse is not None
        assert hook.postToolUse.toolName == "use_mcp_tool"

        with patch(
            "cline_hooks.handlers.post_tool_use.load_plugins",
            return_value=[_ReadInternalWebsitesPlugin()],
        ):
            _run(hook)
        assert get_research("task-1") == [{"tool": "ReadInternalWebsites", "detail": "https://example.com/x"}]


def _mcp_parameters(server_name: str, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the canonical use_mcp_tool parameters a frontend normalises to.

    Returns:
        Parameters matching the use_mcp_tool schema.
    """
    return {
        "server_name": server_name,
        "tool_name": tool_name,
        "arguments": json.dumps(arguments or {}),
    }


class TestRecordToolUseMcpResolution:
    def test_mcp_research_with_extractor(self) -> None:
        _record_tool_use(
            "task-1",
            "use_mcp_tool",
            _mcp_parameters(
                "builder-mcp",
                "ReadInternalWebsites",
                {"inputs": ["https://example.com/x"]},
            ),
            frozenset(),
            frozenset({"ReadInternalWebsites"}),
            {"ReadInternalWebsites": lambda p: p["inputs"][0]},
        )
        assert get_research("task-1") == [{"tool": "ReadInternalWebsites", "detail": "https://example.com/x"}]

    def test_mcp_research_empty_extractors(self) -> None:
        _record_tool_use(
            "task-1",
            "use_mcp_tool",
            _mcp_parameters(
                "builder-mcp",
                "ReadInternalWebsites",
                {"inputs": ["https://example.com/x"]},
            ),
            frozenset(),
            frozenset({"ReadInternalWebsites"}),
            {},
        )
        assert get_research("task-1") == [{"tool": "ReadInternalWebsites", "detail": ""}]

    def test_mcp_state_write(self) -> None:
        result = _record_tool_use(
            "task-1",
            "use_mcp_tool",
            _mcp_parameters("srv", "SomeWrite"),
            frozenset({"SomeWrite"}),
            frozenset(),
            {},
        )
        assert result == (True, "SomeWrite")

    def test_cline_use_mcp_tool_with_json_arguments(self) -> None:
        _record_tool_use(
            "task-1",
            "use_mcp_tool",
            {
                "server_name": "builder-mcp",
                "tool_name": "InternalSearch",
                "arguments": json.dumps({"query": "foo"}),
            },
            frozenset(),
            frozenset({"InternalSearch"}),
            {"InternalSearch": lambda p: p.get("query", "")},
        )
        assert get_research("task-1") == [{"tool": "InternalSearch", "detail": "foo"}]


class TestMemoryWarningOnSessionEnd:
    def test_warns_when_no_memory_writes(self) -> None:
        hook = _make_hook("use_skill", parameters={"skill": "session-end"})
        result = _run(hook)
        assert result is not None
        context = str(result.get("contextModification", ""))
        assert "No memory writes" in context

    def test_no_warning_when_memory_written(self) -> None:
        record_memory_write("task-1", "create_entities")
        hook = _make_hook("use_skill", parameters={"skill": "session-end"})
        result = _run(hook)
        if result is not None:
            context = str(result.get("contextModification", ""))
            assert "No memory writes" not in context

    def test_no_warning_for_non_session_end_skill(self) -> None:
        hook = _make_hook("use_skill", parameters={"skill": "git-usage"})
        result = _run(hook)
        if result is not None:
            context = str(result.get("contextModification", ""))
            assert "No memory writes" not in context


class TestRetrospectiveCounter:
    def test_session_end_increments_counter(self) -> None:
        _run(_make_hook("use_skill", parameters={"skill": "session-end"}))
        assert get_count() == 1

    def test_handoff_increments_counter(self) -> None:
        _run(_make_hook("use_skill", parameters={"skill": "handoff"}))
        assert get_count() == 1

    def test_session_end_then_handoff_counts_once(self) -> None:
        _run(_make_hook("use_skill", parameters={"skill": "session-end"}))
        _run(_make_hook("use_skill", parameters={"skill": "handoff"}))
        assert get_count() == 1

    def test_non_wrap_up_skill_does_not_increment(self) -> None:
        _run(_make_hook("use_skill", parameters={"skill": "git-usage"}))
        assert get_count() == 0

    def test_reminder_fires_at_threshold(self) -> None:
        for i in range(_RETRO_THRESHOLD - 1):
            record_session(f"seed-{i}")
        result = _run(_make_hook("use_skill", parameters={"skill": "session-end"}))
        assert result is not None
        context = str(result.get("contextModification", ""))
        assert "sessions since your last /retrospective" in context

    def test_no_reminder_below_threshold(self) -> None:
        record_memory_write("task-1", "create_entities")
        result = _run(_make_hook("use_skill", parameters={"skill": "session-end"}))
        if result is not None:
            context = str(result.get("contextModification", ""))
            assert "since your last /retrospective" not in context

    def test_memory_warning_and_reminder_coexist(self) -> None:
        for i in range(_RETRO_THRESHOLD - 1):
            record_session(f"seed-{i}")
        result = _run(_make_hook("use_skill", parameters={"skill": "session-end"}))
        assert result is not None
        context = str(result.get("contextModification", ""))
        assert "No memory writes" in context
        assert "since your last /retrospective" in context


class _ReplacingPlugin(HooksPlugin):
    def get_tooling_note(self, workspace_roots: list[str]) -> ToolingNote | None:
        return ToolingNote(note="PLUGIN NOTE", replaces_generic=True)


class _AdditivePlugin(HooksPlugin):
    def get_tooling_note(self, workspace_roots: list[str]) -> ToolingNote | None:
        return ToolingNote(note="ADDITIVE NOTE", replaces_generic=False)


class TestWorkspaceChangeToolingNote:
    def test_note_fires_when_cwd_changes(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with patch(
            "cline_hooks.handlers.git_context.get_generic_tooling_note",
            return_value="TOOLING NOTE",
        ):
            result = _run(
                _make_hook(
                    "Read",
                    parameters={"file_path": "/x.py"},
                    workspace_roots=[str(tmp_path)],
                )
            )
        assert result is not None
        note = cast("str", result.get("contextModification", ""))
        assert "TOOLING NOTE" in note
        assert "Working directory changed" in note

    def test_note_suppressed_when_plugin_replaces_tooling(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with (
            patch(
                "cline_hooks.handlers.git_context.get_generic_tooling_note",
                return_value="TOOLING NOTE",
            ),
            patch(
                "cline_hooks.handlers.post_tool_use.load_plugins",
                return_value=[_ReplacingPlugin()],
            ),
        ):
            result = _run(
                _make_hook(
                    "Read",
                    parameters={"file_path": "/x.py"},
                    workspace_roots=[str(tmp_path)],
                )
            )
        assert result is None or "TOOLING NOTE" not in cast("str", result.get("contextModification", ""))

    def test_additive_note_fires_on_cwd_change(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with (
            patch(
                "cline_hooks.handlers.git_context.get_generic_tooling_note",
                return_value=None,
            ),
            patch(
                "cline_hooks.handlers.post_tool_use.load_plugins",
                return_value=[_AdditivePlugin()],
            ),
        ):
            result = _run(
                _make_hook(
                    "Read",
                    parameters={"file_path": "/x.py"},
                    workspace_roots=[str(tmp_path)],
                )
            )
        assert result is not None
        note = cast("str", result.get("contextModification", ""))
        assert "ADDITIVE NOTE" in note
        assert "Working directory changed" in note

    def test_no_note_on_first_tool_call(self, tmp_path: Path) -> None:
        with patch(
            "cline_hooks.handlers.git_context.get_generic_tooling_note",
            return_value="TOOLING NOTE",
        ):
            result = _run(
                _make_hook(
                    "Read",
                    parameters={"file_path": "/x.py"},
                    workspace_roots=[str(tmp_path)],
                )
            )
        assert result is None or "TOOLING NOTE" not in cast("str", result.get("contextModification", ""))

    def test_no_repeat_note_for_same_cwd(self, tmp_path: Path) -> None:
        record_workspace("task-1", [str(tmp_path)])
        with patch(
            "cline_hooks.handlers.git_context.get_generic_tooling_note",
            return_value="TOOLING NOTE",
        ):
            result = _run(
                _make_hook(
                    "Read",
                    parameters={"file_path": "/x.py"},
                    workspace_roots=[str(tmp_path)],
                )
            )
        assert result is None or "TOOLING NOTE" not in cast("str", result.get("contextModification", ""))

    def test_note_fires_once_then_stops(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with patch(
            "cline_hooks.handlers.git_context.get_generic_tooling_note",
            return_value="TOOLING NOTE",
        ):
            first = _run(
                _make_hook(
                    "Read",
                    parameters={"file_path": "/x.py"},
                    workspace_roots=[str(tmp_path)],
                )
            )
            second = _run(
                _make_hook(
                    "Read",
                    parameters={"file_path": "/x.py"},
                    workspace_roots=[str(tmp_path)],
                )
            )
        assert first is not None
        assert "TOOLING NOTE" in cast("str", first.get("contextModification", ""))
        assert second is None or "TOOLING NOTE" not in cast("str", second.get("contextModification", ""))

    def test_note_refires_when_returning_to_previous_dir(self, tmp_path: Path) -> None:
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        record_workspace("task-1", [str(dir_a)])
        with patch(
            "cline_hooks.handlers.git_context.get_generic_tooling_note",
            return_value="TOOLING NOTE",
        ):
            to_b = _run(
                _make_hook(
                    "Read",
                    parameters={"file_path": "/x.py"},
                    workspace_roots=[str(dir_b)],
                )
            )
            back_to_a = _run(
                _make_hook(
                    "Read",
                    parameters={"file_path": "/x.py"},
                    workspace_roots=[str(dir_a)],
                )
            )
        assert to_b is not None
        assert "TOOLING NOTE" in cast("str", to_b.get("contextModification", ""))
        assert back_to_a is not None
        assert "TOOLING NOTE" in cast("str", back_to_a.get("contextModification", ""))

    def test_no_note_when_new_dir_has_no_marker(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        result = _run(
            _make_hook(
                "Read",
                parameters={"file_path": "/x.py"},
                workspace_roots=[str(tmp_path)],
            )
        )
        assert result is None or "Working directory changed" not in cast("str", result.get("contextModification", ""))

    def test_unhandled_tool_fires_note(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with patch(
            "cline_hooks.handlers.git_context.get_generic_tooling_note",
            return_value="TOOLING NOTE",
        ):
            result = _run(_make_hook("browser_action", workspace_roots=[str(tmp_path)]))
        assert result is not None
        assert "TOOLING NOTE" in cast("str", result.get("contextModification", ""))

    def test_note_fires_on_same_call_as_bare_cd(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with patch(
            "cline_hooks.handlers.git_context.get_generic_tooling_note",
            return_value="TOOLING NOTE",
        ):
            result = _run(
                _make_hook(
                    "Bash",
                    parameters={"command": f"cd {tmp_path}"},
                    workspace_roots=[str(tmp_path)],
                )
            )
        assert result is not None
        note = cast("str", result.get("contextModification", ""))
        assert "TOOLING NOTE" in note
        assert "Working directory changed" in note

    def test_memory_warning_wins_over_note(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with patch(
            "cline_hooks.handlers.git_context.get_generic_tooling_note",
            return_value="TOOLING NOTE",
        ):
            result = _run(
                _make_hook(
                    "use_skill",
                    parameters={"skill": "session-end"},
                    workspace_roots=[str(tmp_path)],
                )
            )
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "No memory writes" in context
        assert "TOOLING NOTE" not in context

    def test_build_failed_wins_over_note(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with patch(
            "cline_hooks.handlers.git_context.get_generic_tooling_note",
            return_value="TOOLING NOTE",
        ):
            result = _run(
                _make_hook(
                    "execute_command",
                    result="BUILD FAILED: boom",
                    workspace_roots=[str(tmp_path)],
                )
            )
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "FAILED" in context
        assert "TOOLING NOTE" not in context

    def test_note_deferred_when_higher_priority_wins(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with patch(
            "cline_hooks.handlers.git_context.get_generic_tooling_note",
            return_value="TOOLING NOTE",
        ):
            first = _run(
                _make_hook(
                    "execute_command",
                    result="BUILD FAILED: boom",
                    workspace_roots=[str(tmp_path)],
                )
            )
            second = _run(
                _make_hook(
                    "Read",
                    parameters={"file_path": "/x.py"},
                    workspace_roots=[str(tmp_path)],
                )
            )
        assert first is not None
        assert "TOOLING NOTE" not in cast("str", first.get("contextModification", ""))
        assert second is not None
        assert "TOOLING NOTE" in cast("str", second.get("contextModification", ""))

    def test_failure_defers_note(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with patch(
            "cline_hooks.handlers.git_context.get_generic_tooling_note",
            return_value="TOOLING NOTE",
        ):
            failed = _run(_make_hook("Bash", success=False, workspace_roots=[str(tmp_path)]))
            succeeded = _run(
                _make_hook(
                    "Read",
                    parameters={"file_path": "/x.py"},
                    workspace_roots=[str(tmp_path)],
                )
            )
        assert failed is not None
        assert "TOOLING NOTE" not in cast("str", failed.get("contextModification", ""))
        assert succeeded is not None
        assert "TOOLING NOTE" in cast("str", succeeded.get("contextModification", ""))


class _NotingPlugin(HooksPlugin):
    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        return HookResult(notes=["PLUGIN NOTE"])


class TestPluginNoteDoesNotTruncateLaterChecks:
    def test_plugin_note_does_not_suppress_build_failed_alert(self) -> None:
        hook = _make_hook("execute_command", result="BUILD FAILED: boom")
        with patch(
            "cline_hooks.handlers.post_tool_use.load_plugins",
            return_value=[_NotingPlugin(), BuildToolsPlugin()],
        ):
            result = _run(hook)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "PLUGIN NOTE" in context
        assert "It FAILED" in context

    def test_plugin_note_does_not_suppress_commit_reminder(self) -> None:
        hook = _make_hook("replace_in_file", parameters={"path": "/x.py"})
        with (
            patch(
                "cline_hooks.handlers.post_tool_use.load_plugins",
                return_value=[_NotingPlugin(), NudgesPlugin()],
            ),
            patch(
                "cline_hooks.plugins.nudges._get_diff_line_count",
                return_value=500,
            ),
        ):
            result = _run(hook)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "PLUGIN NOTE" in context
        assert "COMMIT REMINDER" in context

    def test_plugin_note_does_not_suppress_memory_warning(self) -> None:
        hook = _make_hook("use_skill", parameters={"skill": "session-end"})
        with patch(
            "cline_hooks.handlers.post_tool_use.load_plugins",
            return_value=[_NotingPlugin(), PersistencePlugin()],
        ):
            result = _run(hook)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "PLUGIN NOTE" in context
        assert "No memory writes" in context


class _CapturingPlugin(HooksPlugin):
    def __init__(self, scope: str, captured: list[dict[str, object]]) -> None:
        self._scope = scope
        self._captured = captured

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        if hook_name == self._scope:
            self._captured.append(kwargs)
        return None


class TestTrackToolUsePluginScope:
    def test_reaches_plugin_with_documented_kwargs(self) -> None:
        captured: list[dict[str, object]] = []
        hook = _make_hook(
            "use_mcp_tool",
            parameters={"server_name": "s", "tool_name": "t", "arguments": {}},
        )
        with patch(
            "cline_hooks.handlers.post_tool_use.load_plugins",
            return_value=[_CapturingPlugin("TrackToolUse", captured)],
        ):
            _run(hook)
        assert len(captured) == 1
        kwargs = captured[0]
        assert kwargs["task_id"] == "task-1"
        assert kwargs["tool_name"] == "use_mcp_tool"
        assert kwargs["mcp_tool_name"] == "t"
        assert kwargs["is_state_write"] is False
        assert kwargs["workspace_roots"] == ["/workspace"]
        assert kwargs["agent_type"] == ""

    def test_not_reached_on_tool_failure(self) -> None:
        captured: list[dict[str, object]] = []
        hook = _make_hook("execute_command", success=False)
        with patch(
            "cline_hooks.handlers.post_tool_use.load_plugins",
            return_value=[_CapturingPlugin("TrackToolUse", captured)],
        ):
            _run(hook)
        assert captured == []


class TestToolFailedPluginScope:
    def test_reaches_plugin_with_documented_kwargs(self) -> None:
        captured: list[dict[str, object]] = []
        hook = _make_hook("execute_command", success=False, parameters={"command": "boom"})
        with patch(
            "cline_hooks.handlers.post_tool_use.load_plugins",
            return_value=[_CapturingPlugin("ToolFailed", captured)],
        ):
            _run(hook)
        assert len(captured) == 1
        kwargs = captured[0]
        assert kwargs["task_id"] == "task-1"
        assert kwargs["tool_name"] == "execute_command"
        assert kwargs["parameters"] == {"command": "boom"}
        assert kwargs["workspace_roots"] == ["/workspace"]
        assert kwargs["agent_type"] == ""

    def test_plugin_note_merges_with_failure_reminder(self) -> None:
        class _FailureNotingPlugin(HooksPlugin):
            def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
                if hook_name == "ToolFailed":
                    return HookResult(notes=["FAILURE PLUGIN NOTE"])
                return None

        hook = _make_hook("execute_command", success=False)
        with patch(
            "cline_hooks.handlers.post_tool_use.load_plugins",
            return_value=[_FailureNotingPlugin(), PersistencePlugin()],
        ):
            result = _run(hook)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "FAILURE PLUGIN NOTE" in context
        assert "persist" in context.lower()
