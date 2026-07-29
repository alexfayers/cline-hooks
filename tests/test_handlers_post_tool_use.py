from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import patch

from cline_hooks.core.models import HookInputPostToolUse
from cline_hooks.core.plugin import HooksPlugin, ToolingNote
from cline_hooks.frontends.cline import parse_cline_data as parse_data
from cline_hooks.handlers.post_tool_use import (
    _RETRO_THRESHOLD,
    _extract_research_detail,
    _get_all_research_detail_extractors,
    _get_all_research_tool_names,
    _is_session_end_skill,
    _is_wrap_up_skill,
    _record_tool_use,
    handle_post_tool_use,
)
from cline_hooks.state.memory import record_memory_write
from cline_hooks.state.research import get_research
from cline_hooks.state.retrospective import get_count, record_session
from cline_hooks.state.workspace import record_workspace

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_BASE = {
    "clineVersion": "1.0",
    "timestamp": "2024-01-01T00:00:00Z",
    "taskId": "task-1",
    "userId": "user-1",
    "workspaceRoots": ["/workspace"],
    "hookName": "PostToolUse",
}


def _make_hook(
    tool_name: str,
    success: bool = True,
    result: str | None = None,
    parameters: dict[str, object] | None = None,
    workspace_roots: list[str] | None = None,
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
    hook = parse_data(json.dumps(data))
    assert isinstance(hook, HookInputPostToolUse)
    return hook


def _run(hook: HookInputPostToolUse) -> dict[str, object] | None:
    output: list[str] = []
    try:
        with patch("builtins.print", side_effect=lambda s, **kw: output.append(s)):
            handle_post_tool_use(hook)
    except SystemExit:
        pass
    if not output:
        return None
    return cast("dict[str, object]", json.loads(output[0]))


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
            patch("cline_hooks.handlers.post_tool_use.collect_hook_results", side_effect=_fake_collect),
            patch("builtins.print"),
        ):
            handle_post_tool_use(hook)
        assert captured
        assert captured[0].get("agent_type") == "Explore"


class TestSkillDetectionViaRead:
    def test_skill_md_read_records_skill(self) -> None:
        hook = _make_hook("read_file", parameters={"path": "/home/user/.kiro/skills/git-usage/SKILL.md"})
        with patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "git-usage")

    def test_non_skill_read_does_not_record(self) -> None:
        hook = _make_hook("read_file", parameters={"path": "/home/user/project/README.md"})
        with patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_record:
            _run(hook)
        mock_record.assert_not_called()

    def test_skill_md_in_nested_path(self) -> None:
        hook = _make_hook("read_file", parameters={"path": "/deep/nested/skills/pre-implementation/SKILL.md"})
        with patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "pre-implementation")

    def test_empty_path_does_not_record(self) -> None:
        hook = _make_hook("read_file", parameters={})
        with patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_record:
            _run(hook)
        mock_record.assert_not_called()

    def test_claude_code_read_skill_detected(self) -> None:
        hook = _make_hook("Read", parameters={"file_path": "/Users/me/.claude/skills/git-usage/SKILL.md"})
        with patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "git-usage")


class TestSkillDetectionViaShellCommand:
    def test_cat_skill_md_records_skill(self) -> None:
        hook = _make_hook(
            "Bash",
            parameters={"command": "cat /Users/me/.codex/skills/git-usage/SKILL.md"},
        )
        with patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "git-usage")

    def test_sed_skill_md_records_skill(self) -> None:
        hook = _make_hook(
            "Bash",
            parameters={"command": "sed -n '1,260p' /a/b/skills/pre-implementation/SKILL.md"},
        )
        with patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "pre-implementation")

    def test_execute_command_skill_md_records_skill(self) -> None:
        hook = _make_hook(
            "execute_command",
            parameters={"command": "less /deep/skills/cr/SKILL.md"},
        )
        with patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "cr")

    def test_git_command_does_not_record_skill(self) -> None:
        hook = _make_hook("Bash", parameters={"command": "git -P status --short"})
        with patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_record:
            _run(hook)
        mock_record.assert_not_called()

    def test_bare_skill_md_reference_does_not_record(self) -> None:
        hook = _make_hook("Bash", parameters={"command": "find . -name SKILL.md"})
        with patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_record:
            _run(hook)
        mock_record.assert_not_called()


class TestAgentUseRecording:
    def test_agent_tool_records_use(self) -> None:
        hook = _make_hook("Agent", parameters={"description": "research"})
        with patch("cline_hooks.handlers.post_tool_use._record_agent_use") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "Agent")

    def test_new_task_records_use(self) -> None:
        hook = _make_hook("new_task", parameters={})
        with patch("cline_hooks.handlers.post_tool_use._record_agent_use") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "new_task")

    def test_non_agent_tool_does_not_record(self) -> None:
        hook = _make_hook("Bash", parameters={"command": "echo hi"})
        with patch("cline_hooks.handlers.post_tool_use._record_agent_use") as mock_record:
            _run(hook)
        mock_record.assert_not_called()

    def test_agent_tool_does_not_record_skill_or_memory(self) -> None:
        hook = _make_hook("Agent", parameters={"description": "research"})
        with (
            patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_skill,
            patch("cline_hooks.handlers.post_tool_use._record_memory_write") as mock_memory,
        ):
            _run(hook)
        mock_skill.assert_not_called()
        mock_memory.assert_not_called()


class TestGetAllResearchToolNames:
    def test_defaults_present_with_no_plugins(self) -> None:
        assert _get_all_research_tool_names([]) == frozenset({"WebFetch", "WebSearch"})

    def test_union_with_plugin_names(self) -> None:
        class ResearchPlugin(HooksPlugin):
            def get_research_tool_names(self) -> frozenset[str]:
                return frozenset({"InternalSearch", "InternalCodeSearch"})

        result = _get_all_research_tool_names([ResearchPlugin()])
        assert result == frozenset({"WebFetch", "WebSearch", "InternalSearch", "InternalCodeSearch"})


class TestGetAllResearchDetailExtractors:
    def test_empty_with_no_plugins(self) -> None:
        assert _get_all_research_detail_extractors([]) == {}

    def test_merges_from_plugin(self) -> None:
        class ExtractorPlugin(HooksPlugin):
            def get_research_detail_extractors(self) -> dict[str, Callable[[dict[str, Any]], str]]:
                return {"InternalSearch": lambda p: p.get("query", "")}

        result = _get_all_research_detail_extractors([ExtractorPlugin()])
        assert set(result) == {"InternalSearch"}

    def test_last_plugin_wins_on_collision(self) -> None:
        class PluginA(HooksPlugin):
            def get_research_detail_extractors(self) -> dict[str, Callable[[dict[str, Any]], str]]:
                return {"X": lambda _p: "a"}

        class PluginB(HooksPlugin):
            def get_research_detail_extractors(self) -> dict[str, Callable[[dict[str, Any]], str]]:
                return {"X": lambda _p: "b"}

        result = _get_all_research_detail_extractors([PluginA(), PluginB()])
        assert result["X"]({}) == "b"


class TestExtractResearchDetail:
    def test_extractor_used_when_present(self) -> None:
        assert _extract_research_detail("X", {"k": "v"}, {"X": lambda p: p["k"]}) == "v"  # noqa: FURB118

    def test_webfetch_fallback(self) -> None:
        assert _extract_research_detail("WebFetch", {"url": "u"}, {}) == "u"

    def test_websearch_fallback(self) -> None:
        assert _extract_research_detail("WebSearch", {"query": "q"}, {}) == "q"

    def test_unknown_tool_returns_empty(self) -> None:
        assert _extract_research_detail("Unknown", {"url": "u"}, {}) == ""

    def test_extractor_raises_returns_empty(self) -> None:
        def _boom(_p: dict[str, Any]) -> str:
            msg = "boom"
            raise RuntimeError(msg)

        assert _extract_research_detail("X", {}, {"X": _boom}) == ""

    def test_extractor_returns_none_coerced_empty(self) -> None:
        def _none(_p: dict[str, Any]) -> str:
            return cast("str", None)

        assert _extract_research_detail("X", {}, {"X": _none}) == ""


class TestResearchRecording:
    def test_webfetch_records_url(self) -> None:
        _run(_make_hook("WebFetch", parameters={"url": "https://example.com/docs"}))
        assert get_research("task-1") == [{"tool": "WebFetch", "detail": "https://example.com/docs"}]

    def test_websearch_records_query(self) -> None:
        _run(_make_hook("WebSearch", parameters={"query": "python entry points"}))
        assert get_research("task-1") == [{"tool": "WebSearch", "detail": "python entry points"}]

    def test_non_research_tool_records_nothing(self) -> None:
        _run(_make_hook("Read", parameters={"file_path": "/x.py"}))
        assert get_research("task-1") == []

    def test_failed_research_tool_records_nothing(self) -> None:
        _run(_make_hook("WebFetch", success=False, parameters={"url": "https://example.com"}))
        assert get_research("task-1") == []


class TestClaudeCodeMcpResearchIntegration:
    def test_prefixed_mcp_tool_records_research_via_plugin(self) -> None:
        class ResearchPlugin(HooksPlugin):
            def get_research_tool_names(self) -> frozenset[str]:
                return frozenset({"ReadInternalWebsites"})

            def get_research_detail_extractors(self) -> dict[str, Callable[[dict[str, Any]], str]]:
                return {"ReadInternalWebsites": lambda p: p.get("inputs", [""])[0]}

        hook = _make_hook(
            "mcp__builder-mcp__ReadInternalWebsites",
            parameters={"inputs": ["https://example.com/x"]},
        )
        with patch("cline_hooks.handlers.post_tool_use.load_plugins", return_value=[ResearchPlugin()]):
            _run(hook)
        assert get_research("task-1") == [{"tool": "ReadInternalWebsites", "detail": "https://example.com/x"}]


class TestRecordToolUseMcpResolution:
    def test_prefixed_mcp_research_with_extractor(self) -> None:
        _record_tool_use(
            "task-1",
            "mcp__builder-mcp__ReadInternalWebsites",
            {"inputs": ["https://example.com/x"]},
            frozenset(),
            frozenset({"ReadInternalWebsites"}),
            {"ReadInternalWebsites": lambda p: p["inputs"][0]},
        )
        assert get_research("task-1") == [{"tool": "ReadInternalWebsites", "detail": "https://example.com/x"}]

    def test_prefixed_mcp_research_empty_extractors(self) -> None:
        _record_tool_use(
            "task-1",
            "mcp__builder-mcp__ReadInternalWebsites",
            {"inputs": ["https://example.com/x"]},
            frozenset(),
            frozenset({"ReadInternalWebsites"}),
            {},
        )
        assert get_research("task-1") == [{"tool": "ReadInternalWebsites", "detail": ""}]

    def test_prefixed_mcp_state_write(self) -> None:
        result = _record_tool_use(
            "task-1",
            "mcp__srv__SomeWrite",
            {},
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


class TestIsSessionEndSkill:
    def test_claude_code_skill_tool(self) -> None:
        assert _is_session_end_skill("Skill", {"skill": "session-end"})

    def test_cline_use_skill(self) -> None:
        assert _is_session_end_skill("use_skill", {"skill_name": "session-end"})

    def test_read_skill_md(self) -> None:
        assert _is_session_end_skill("read_file", {"path": "/home/user/.kiro/skills/session-end/SKILL.md"})

    def test_claude_code_read_skill_md(self) -> None:
        assert _is_session_end_skill("Read", {"file_path": "/Users/me/.claude/skills/session-end/SKILL.md"})

    def test_other_skill_not_detected(self) -> None:
        assert not _is_session_end_skill("Skill", {"skill": "git-usage"})

    def test_unrelated_tool_not_detected(self) -> None:
        assert not _is_session_end_skill("Bash", {"command": "echo hi"})


class TestMemoryWarningOnSessionEnd:
    def test_warns_when_no_memory_writes(self) -> None:
        hook = _make_hook("Skill", parameters={"skill": "session-end"})
        result = _run(hook)
        assert result is not None
        context = str(result.get("contextModification", ""))
        assert "No memory writes" in context

    def test_no_warning_when_memory_written(self) -> None:
        record_memory_write("task-1", "create_entities")
        hook = _make_hook("Skill", parameters={"skill": "session-end"})
        result = _run(hook)
        if result is not None:
            context = str(result.get("contextModification", ""))
            assert "No memory writes" not in context

    def test_no_warning_for_non_session_end_skill(self) -> None:
        hook = _make_hook("Skill", parameters={"skill": "git-usage"})
        result = _run(hook)
        if result is not None:
            context = str(result.get("contextModification", ""))
            assert "No memory writes" not in context


class TestIsWrapUpSkill:
    def test_session_end_is_wrap_up(self) -> None:
        assert _is_wrap_up_skill("Skill", {"skill": "session-end"})

    def test_handoff_is_wrap_up(self) -> None:
        assert _is_wrap_up_skill("Skill", {"skill": "handoff"})

    def test_handoff_via_read(self) -> None:
        assert _is_wrap_up_skill("Read", {"file_path": "/Users/me/.claude/skills/handoff/SKILL.md"})

    def test_unrelated_skill_not_wrap_up(self) -> None:
        assert not _is_wrap_up_skill("Skill", {"skill": "git-usage"})

    def test_unrelated_tool_not_wrap_up(self) -> None:
        assert not _is_wrap_up_skill("Bash", {"command": "echo hi"})


class TestRetrospectiveCounter:
    def test_session_end_increments_counter(self) -> None:
        _run(_make_hook("Skill", parameters={"skill": "session-end"}))
        assert get_count() == 1

    def test_handoff_increments_counter(self) -> None:
        _run(_make_hook("Skill", parameters={"skill": "handoff"}))
        assert get_count() == 1

    def test_session_end_then_handoff_counts_once(self) -> None:
        _run(_make_hook("Skill", parameters={"skill": "session-end"}))
        _run(_make_hook("Skill", parameters={"skill": "handoff"}))
        assert get_count() == 1

    def test_non_wrap_up_skill_does_not_increment(self) -> None:
        _run(_make_hook("Skill", parameters={"skill": "git-usage"}))
        assert get_count() == 0

    def test_reminder_fires_at_threshold(self) -> None:
        for i in range(_RETRO_THRESHOLD - 1):
            record_session(f"seed-{i}")
        result = _run(_make_hook("Skill", parameters={"skill": "session-end"}))
        assert result is not None
        context = str(result.get("contextModification", ""))
        assert "sessions since your last /retrospective" in context

    def test_no_reminder_below_threshold(self) -> None:
        record_memory_write("task-1", "create_entities")
        result = _run(_make_hook("Skill", parameters={"skill": "session-end"}))
        if result is not None:
            context = str(result.get("contextModification", ""))
            assert "since your last /retrospective" not in context

    def test_memory_warning_and_reminder_coexist(self) -> None:
        for i in range(_RETRO_THRESHOLD - 1):
            record_session(f"seed-{i}")
        result = _run(_make_hook("Skill", parameters={"skill": "session-end"}))
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
        with patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"):
            result = _run(_make_hook("Read", parameters={"file_path": "/x.py"}, workspace_roots=[str(tmp_path)]))
        assert result is not None
        note = cast("str", result.get("contextModification", ""))
        assert "TOOLING NOTE" in note
        assert "Working directory changed" in note

    def test_note_suppressed_when_plugin_replaces_tooling(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with (
            patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"),
            patch("cline_hooks.handlers.post_tool_use.load_plugins", return_value=[_ReplacingPlugin()]),
        ):
            result = _run(_make_hook("Read", parameters={"file_path": "/x.py"}, workspace_roots=[str(tmp_path)]))
        assert result is None or "TOOLING NOTE" not in cast("str", result.get("contextModification", ""))

    def test_additive_note_fires_on_cwd_change(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with (
            patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value=None),
            patch("cline_hooks.handlers.post_tool_use.load_plugins", return_value=[_AdditivePlugin()]),
        ):
            result = _run(_make_hook("Read", parameters={"file_path": "/x.py"}, workspace_roots=[str(tmp_path)]))
        assert result is not None
        note = cast("str", result.get("contextModification", ""))
        assert "ADDITIVE NOTE" in note
        assert "Working directory changed" in note

    def test_no_note_on_first_tool_call(self, tmp_path: Path) -> None:
        with patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"):
            result = _run(_make_hook("Read", parameters={"file_path": "/x.py"}, workspace_roots=[str(tmp_path)]))
        assert result is None or "TOOLING NOTE" not in cast("str", result.get("contextModification", ""))

    def test_no_repeat_note_for_same_cwd(self, tmp_path: Path) -> None:
        record_workspace("task-1", [str(tmp_path)])
        with patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"):
            result = _run(_make_hook("Read", parameters={"file_path": "/x.py"}, workspace_roots=[str(tmp_path)]))
        assert result is None or "TOOLING NOTE" not in cast("str", result.get("contextModification", ""))

    def test_note_fires_once_then_stops(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"):
            first = _run(_make_hook("Read", parameters={"file_path": "/x.py"}, workspace_roots=[str(tmp_path)]))
            second = _run(_make_hook("Read", parameters={"file_path": "/x.py"}, workspace_roots=[str(tmp_path)]))
        assert first is not None
        assert "TOOLING NOTE" in cast("str", first.get("contextModification", ""))
        assert second is None or "TOOLING NOTE" not in cast("str", second.get("contextModification", ""))

    def test_note_refires_when_returning_to_previous_dir(self, tmp_path: Path) -> None:
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        record_workspace("task-1", [str(dir_a)])
        with patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"):
            to_b = _run(_make_hook("Read", parameters={"file_path": "/x.py"}, workspace_roots=[str(dir_b)]))
            back_to_a = _run(_make_hook("Read", parameters={"file_path": "/x.py"}, workspace_roots=[str(dir_a)]))
        assert to_b is not None
        assert "TOOLING NOTE" in cast("str", to_b.get("contextModification", ""))
        assert back_to_a is not None
        assert "TOOLING NOTE" in cast("str", back_to_a.get("contextModification", ""))

    def test_no_note_when_new_dir_has_no_marker(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        result = _run(_make_hook("Read", parameters={"file_path": "/x.py"}, workspace_roots=[str(tmp_path)]))
        assert result is None or "Working directory changed" not in cast("str", result.get("contextModification", ""))

    def test_unhandled_tool_fires_note(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"):
            result = _run(_make_hook("browser_action", workspace_roots=[str(tmp_path)]))
        assert result is not None
        assert "TOOLING NOTE" in cast("str", result.get("contextModification", ""))

    def test_note_fires_on_same_call_as_bare_cd(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"):
            result = _run(_make_hook("Bash", parameters={"command": f"cd {tmp_path}"}, workspace_roots=[str(tmp_path)]))
        assert result is not None
        note = cast("str", result.get("contextModification", ""))
        assert "TOOLING NOTE" in note
        assert "Working directory changed" in note

    def test_memory_warning_wins_over_note(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"):
            result = _run(_make_hook("Skill", parameters={"skill": "session-end"}, workspace_roots=[str(tmp_path)]))
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "No memory writes" in context
        assert "TOOLING NOTE" not in context

    def test_build_failed_wins_over_note(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"):
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
        with patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"):
            first = _run(
                _make_hook(
                    "execute_command",
                    result="BUILD FAILED: boom",
                    workspace_roots=[str(tmp_path)],
                )
            )
            second = _run(_make_hook("Read", parameters={"file_path": "/x.py"}, workspace_roots=[str(tmp_path)]))
        assert first is not None
        assert "TOOLING NOTE" not in cast("str", first.get("contextModification", ""))
        assert second is not None
        assert "TOOLING NOTE" in cast("str", second.get("contextModification", ""))

    def test_failure_defers_note(self, tmp_path: Path) -> None:
        record_workspace("task-1", ["/old"])
        with patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"):
            failed = _run(_make_hook("Bash", success=False, workspace_roots=[str(tmp_path)]))
            succeeded = _run(_make_hook("Read", parameters={"file_path": "/x.py"}, workspace_roots=[str(tmp_path)]))
        assert failed is not None
        assert "TOOLING NOTE" not in cast("str", failed.get("contextModification", ""))
        assert succeeded is not None
        assert "TOOLING NOTE" in cast("str", succeeded.get("contextModification", ""))
