from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import git
import pytest

from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.protocol import RawPayload, get_protocol
from cline_hooks.core.response import render
from cline_hooks.frontends.cline import ClineProtocol
from cline_hooks.handlers.pre_tool_use import handle_pre_tool_use
from cline_hooks.plugins.managed_files import _is_managed_path
from cline_hooks.plugins.tool_guards import ToolGuardsPlugin, _starts_with_emoji
from cline_hooks.state.skills import record_skill
from cline_hooks.state.store import TaskStateStore

if TYPE_CHECKING:
    import logging
    from pathlib import Path

    from pytest_mock import MockerFixture

    from cline_hooks.core.models import HookInput, HookInputPreToolUse


def parse_data(raw: str) -> HookInput:
    return ClineProtocol().parse(RawPayload.from_stdin(raw))


_BASE = {
    "clineVersion": "1.0.0",
    "timestamp": "0",
    "taskId": "task-1",
    "userId": "user-1",
    "workspaceRoots": [],
    "hookName": "PreToolUse",
}


def _make_hook(
    tool_name: str,
    parameters: dict[str, object],
    workspace_roots: list[str] | None = None,
) -> HookInputPreToolUse:
    return cast(
        "HookInputPreToolUse",
        parse_data(
            json.dumps({
                **_BASE,
                "workspaceRoots": workspace_roots if workspace_roots is not None else [],
                "preToolUse": {"toolName": tool_name, "parameters": parameters},
            })
        ),
    )


def _run(
    tool_name: str,
    parameters: dict[str, object],
    workspace_roots: list[str] | None = None,
) -> dict[str, object] | None:
    hook = _make_hook(tool_name, parameters, workspace_roots)
    outcome = handle_pre_tool_use(hook)
    if outcome is None or outcome.message is None:
        return None
    response = render(outcome, get_protocol())
    if not response.stdout:
        return None
    return cast("dict[str, object]", json.loads(response.stdout))


def _init_clean_repo(path: Path) -> None:
    """Init a git repo at path with one committed file, leaving the tree clean."""
    repo = git.Repo.init(path)
    (path / "committed.txt").write_text("content")
    repo.index.add(["committed.txt"])
    author = git.Actor("Test", "test@example.com")
    repo.index.commit("initial", author=author, committer=author)


class TestStartsWithEmoji:
    @pytest.mark.parametrize(
        "text",
        [
            "👋 hello",
            "🎯 plan",
            "  🔧 with leading space",
            "\t🐍 tab prefix",
        ],
    )
    def test_returns_true_for_emoji_start(self, text: str) -> None:
        assert _starts_with_emoji(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "Hello",
            "no emoji here",
            "  plain text",
            "",
            "   ",
        ],
    )
    def test_returns_false_for_ascii_start(self, text: str) -> None:
        assert _starts_with_emoji(text) is False


class TestGrepBlock:
    def test_grep_with_build_command_is_blocked(self) -> None:
        result = _run("execute_command", {"command": "just | grep foo"})
        assert result is not None
        assert "build output" in cast("str", result.get("errorMessage", ""))

    def test_grep_standalone_is_not_blocked(self) -> None:
        result = _run("execute_command", {"command": "grep -r foo ."})
        assert result is None

    def test_grep_piped_to_non_build_is_not_blocked(self) -> None:
        result = _run("execute_command", {"command": "ps aux | grep python"})
        assert result is None

    def test_grep_with_just_is_blocked(self) -> None:
        result = _run("execute_command", {"command": "just build | grep ERROR"})
        assert result is not None

    def test_grep_without_build_not_blocked(self) -> None:
        result = _run("execute_command", {"command": "cat file.txt | grep foo"})
        assert result is None

    def test_non_grep_command_is_not_blocked(self) -> None:
        result = _run("execute_command", {"command": "ls -la"})
        assert result is None


class TestHeadTailBlock:
    def test_head_with_build_is_blocked(self) -> None:
        result = _run("execute_command", {"command": "just | head -n 10"})
        assert result is not None
        assert "full output" in cast("str", result.get("errorMessage", ""))

    def test_head_standalone_is_blocked(self) -> None:
        result = _run("execute_command", {"command": "head -n 10 file.txt"})
        assert result is not None
        assert "Read tool" in cast("str", result.get("errorMessage", ""))

    def test_head_piped_to_non_build_not_blocked(self) -> None:
        result = _run("execute_command", {"command": "ls | head"})
        assert result is None

    def test_tail_with_build_is_blocked(self) -> None:
        result = _run("execute_command", {"command": "just | tail -n 20"})
        assert result is not None
        assert "full output" in cast("str", result.get("errorMessage", ""))

    def test_tail_standalone_is_blocked(self) -> None:
        result = _run("execute_command", {"command": "tail -n 20 file.log"})
        assert result is not None
        assert "Read tool" in cast("str", result.get("errorMessage", ""))

    def test_tail_follow_without_build_not_blocked(self) -> None:
        result = _run("execute_command", {"command": "tail -f service.log"})
        assert result is None

    def test_tail_follow_uppercase_not_blocked(self) -> None:
        result = _run("execute_command", {"command": "tail -F service.log"})
        assert result is None

    def test_tail_combined_follow_flag_not_blocked(self) -> None:
        result = _run("execute_command", {"command": "tail -100f service.log"})
        assert result is None


class TestCatBlock:
    def test_standalone_cat_is_blocked(self) -> None:
        result = _run("execute_command", {"command": "cat /path/to/file.py"})
        assert result is not None
        assert "Read tool" in cast("str", result.get("errorMessage", ""))

    def test_cat_piped_to_other_command_is_allowed(self) -> None:
        result = _run("execute_command", {"command": "cat file.json | python3 -c 'import json'"})
        assert result is None

    def test_cat_piped_to_grep_is_allowed(self) -> None:
        result = _run("execute_command", {"command": "cat file.txt | grep foo"})
        assert result is None


class TestCommandRules:
    def test_rm_f_blocked(self) -> None:
        result = _run("execute_command", {"command": "rm -f file.txt"})
        assert result is not None
        assert "rm -f" in cast("str", result.get("errorMessage", "")).lower()

    def test_safe_command_allowed(self) -> None:
        result = _run("execute_command", {"command": "ls -la"})
        assert result is None


class TestEchoTrueBlock:
    def test_standalone_true_is_blocked(self) -> None:
        result = _run("execute_command", {"command": "true"})
        assert result is not None
        assert "standalone" in cast("str", result.get("errorMessage", "")).lower()

    def test_true_after_or_suppression_is_allowed(self) -> None:
        result = _run("execute_command", {"command": "some_cmd || true"})
        assert result is None

    def test_standalone_echo_is_blocked(self) -> None:
        result = _run("execute_command", {"command": "echo abc"})
        assert result is not None
        assert "standalone" in cast("str", result.get("errorMessage", "")).lower()

    def test_echo_piped_to_other_command_is_allowed(self) -> None:
        result = _run("execute_command", {"command": 'echo "x" | grep x'})
        assert result is None

    def test_echo_chained_with_other_command_is_allowed(self) -> None:
        result = _run("execute_command", {"command": 'echo "starting" && npm test'})
        assert result is None


class TestPlanModeRespondEmojiCheck:
    def test_emoji_start_is_allowed(self) -> None:
        result = _run("plan_mode_respond", {"response": "👋 Hey there!"})
        assert result is None

    def test_ascii_start_is_blocked(self) -> None:
        result = _run("plan_mode_respond", {"response": "Hey there!"})
        assert result is not None
        assert "emoji" in cast("str", result.get("errorMessage", "")).lower()

    def test_empty_response_is_blocked(self) -> None:
        result = _run("plan_mode_respond", {"response": ""})
        assert result is not None

    def test_whitespace_only_response_is_blocked(self) -> None:
        result = _run("plan_mode_respond", {"response": "   "})
        assert result is not None

    def test_whitespace_then_emoji_is_allowed(self) -> None:
        result = _run("plan_mode_respond", {"response": "  🎯 with indent"})
        assert result is None

    def test_new_task_mentioned_in_block_message(self) -> None:
        result = _run("plan_mode_respond", {"response": "No emoji"})
        assert result is not None
        assert "new_task" in cast("str", result.get("errorMessage", ""))


class TestClearBlocksOnPass:
    def test_stale_block_cleared_after_successful_run(self) -> None:
        store = TaskStateStore()
        store.record_block("task-1", "execute_command", "some old reason")
        assert len(store.get_blocks("task-1")) == 1
        _run("execute_command", {"command": "ls -la"})
        assert store.get_blocks("task-1") == []

    def test_no_stale_blocks_when_no_previous_blocks(self) -> None:
        store = TaskStateStore()
        _run("execute_command", {"command": "ls -la"})
        assert store.get_blocks("task-1") == []


class TestForwardsAgentType:
    def _run_capturing_kwargs(self, agent_type: str) -> list[dict[str, object]]:
        captured: list[dict[str, object]] = []

        def _fake_collect(_plugins: object, _hook_name: str, **kwargs: object) -> object:
            captured.append(kwargs)
            from cline_hooks.core.plugin import HookResult

            return HookResult()

        hook = cast(
            "HookInputPreToolUse",
            parse_data(
                json.dumps({
                    **_BASE,
                    "agentType": agent_type,
                    "preToolUse": {
                        "toolName": "read_file",
                        "parameters": {"path": "/x.py"},
                    },
                })
            ),
        )
        with (
            patch(
                "cline_hooks.handlers.pre_tool_use.collect_hook_results",
                side_effect=_fake_collect,
            ),
            patch("builtins.print"),
            contextlib.suppress(SystemExit),
        ):
            handle_pre_tool_use(hook)
        return captured

    def test_agent_type_forwarded_to_plugins(self) -> None:
        captured = self._run_capturing_kwargs("Explore")
        assert captured
        assert all(kw.get("agent_type") == "Explore" for kw in captured)

    def test_empty_agent_type_forwarded(self) -> None:
        captured = self._run_capturing_kwargs("")
        assert captured
        assert all(kw.get("agent_type") == "" for kw in captured)


class TestGitPushMarkerBlock:
    def test_push_without_marker_is_allowed(self) -> None:
        record_skill("task-1", "git-usage")
        result = _run("execute_command", {"command": "git push"})
        assert result is None

    def test_push_via_absolute_git_path_without_marker_is_allowed(self) -> None:
        record_skill("task-1", "git-usage")
        result = _run("execute_command", {"command": "/usr/bin/git push"})
        assert result is None

    def test_marker_blocks_push(self, tmp_path: Path, mocker: MockerFixture) -> None:
        record_skill("task-1", "git-usage")
        (tmp_path / "some-marker").mkdir()
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        git.Repo.init(repo_dir)
        mocker.patch(
            "cline_hooks.handlers.push_guard.get_push_block_markers",
            return_value=("some-marker",),
        )
        result = _run("execute_command", {"command": "git push"}, workspace_roots=[str(repo_dir)])
        assert result is not None
        assert "managed workspace" in cast("str", result.get("errorMessage", ""))


class TestManagedFileWriteGuard:
    _MANAGED_FILE = "/Users/test/.claude/rules/managed-rule.md"

    @pytest.fixture(autouse=True)
    def _mock_managed_files(self) -> None:
        import cline_hooks.plugins.managed_files as module

        module._managed_files = {self._MANAGED_FILE}

    def test_is_managed_path_returns_true_for_managed_file(self) -> None:
        assert _is_managed_path(self._MANAGED_FILE) is True

    def test_is_managed_path_returns_false_for_unmanaged(self) -> None:
        assert _is_managed_path("/some/random/file.md") is False

    def test_is_managed_path_returns_false_for_unmanaged_in_same_dir(self) -> None:
        assert _is_managed_path("/Users/test/.claude/rules/my-custom-rule.md") is False

    def test_is_managed_path_handles_invalid_path(self) -> None:
        assert _is_managed_path("") is False

    def test_replace_in_file_blocked_for_managed_file(self) -> None:
        result = _run(
            "replace_in_file",
            {
                "path": self._MANAGED_FILE,
                "diff": "------- SEARCH\n=======\nnew\n+++++++ REPLACE",
            },
        )
        assert result is not None
        assert "source file" in cast("str", result.get("errorMessage", "")).lower()

    def test_replace_in_file_allowed_for_unmanaged_file(self) -> None:
        result = _run(
            "replace_in_file",
            {
                "path": "/Users/test/.claude/rules/my-custom-rule.md",
                "diff": "------- SEARCH\n=======\nnew\n+++++++ REPLACE",
            },
        )
        assert result is None or "source file" not in cast("str", result.get("errorMessage", "")).lower()

    def test_write_to_file_blocked_for_managed_file(self) -> None:
        result = _run(
            "write_to_file",
            {"path": self._MANAGED_FILE, "content": "# overwrite"},
        )
        assert result is not None
        assert "source file" in cast("str", result.get("errorMessage", "")).lower()

    def test_edit_blocked_message_names_resolved_source(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "cline_hooks.plugins.managed_files._get_source_impl",
            return_value="/src/rules/managed-rule.md",
        )
        result = _run(
            "replace_in_file",
            {
                "path": self._MANAGED_FILE,
                "diff": "------- SEARCH\n=======\nnew\n+++++++ REPLACE",
            },
        )
        assert result is not None
        assert "/src/rules/managed-rule.md" in cast("str", result.get("errorMessage", ""))

    def test_edit_blocked_message_falls_back_when_source_unresolved(self, mocker: MockerFixture) -> None:
        mocker.patch("cline_hooks.plugins.managed_files._get_source_impl", return_value=None)
        result = _run(
            "replace_in_file",
            {
                "path": self._MANAGED_FILE,
                "diff": "------- SEARCH\n=======\nnew\n+++++++ REPLACE",
            },
        )
        assert result is not None
        assert cast("str", result.get("errorMessage", "")) == (
            f"{self._MANAGED_FILE} is managed by llm-prompts. MUST edit the source file "
            "instead, then run `llm-prompts update`."
        )

    def test_edit_blocked_message_falls_back_when_source_resolution_raises(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "cline_hooks.plugins.managed_files._get_source_impl",
            side_effect=RuntimeError("boom"),
        )
        result = _run(
            "replace_in_file",
            {
                "path": self._MANAGED_FILE,
                "diff": "------- SEARCH\n=======\nnew\n+++++++ REPLACE",
            },
        )
        assert result is not None
        assert cast("str", result.get("errorMessage", "")) == (
            f"{self._MANAGED_FILE} is managed by llm-prompts. MUST edit the source file "
            "instead, then run `llm-prompts update`."
        )


class _NotePlugin(HooksPlugin):
    """Test double contributing a note to every hook, never a block."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        return HookResult(notes=["plugin note"])


class TestPluginNoteDoesNotSuppressToolCheck:
    def test_plan_mode_respond_check_still_fires(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "cline_hooks.handlers.pre_tool_use.load_plugins",
            return_value=[_NotePlugin(), ToolGuardsPlugin()],
        )
        result = _run("plan_mode_respond", {"response": "No emoji"})
        assert result is not None
        assert "emoji" in cast("str", result.get("errorMessage", "")).lower()

    def test_command_rule_block_still_fires(self, mocker: MockerFixture) -> None:
        from cline_hooks.core.plugin import HookResult

        mocker.patch(
            "cline_hooks.handlers.pre_tool_use.collect_hook_results",
            return_value=HookResult(notes=["plugin note"]),
        )
        result = _run("execute_command", {"command": "rm -f x"})
        assert result is not None
        assert "rm -f" in cast("str", result.get("errorMessage", "")).lower()

    def test_plugin_note_still_reaches_context_modification(self, mocker: MockerFixture) -> None:
        from cline_hooks.core.plugin import HookResult

        mocker.patch(
            "cline_hooks.handlers.pre_tool_use.collect_hook_results",
            return_value=HookResult(notes=["plugin note"]),
        )
        result = _run("execute_command", {"command": "ls -la"})
        assert result is not None
        assert "plugin note" in cast("str", result.get("contextModification", ""))

    def test_plugin_note_accumulates_with_tool_note(self, mocker: MockerFixture) -> None:
        mocker.patch(
            "cline_hooks.handlers.pre_tool_use.load_plugins",
            return_value=[_NotePlugin(), ToolGuardsPlugin()],
        )
        result = _run(
            "replace_in_file",
            {
                "path": "/Users/test/.claude/rules/my-custom-rule.md",
                "diff": ("------- SEARCH\n=======\n# explains why we did this\n+++++++ REPLACE"),
            },
        )
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "plugin note" in context
        assert "MUST NOT write comments explaining the reasoning" in context


class TestDelegationNudgeIntegration:
    def test_fires_for_write_to_file(self, mocker: MockerFixture) -> None:
        mocker.patch.dict("os.environ", {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}, clear=True)
        result = _run("write_to_file", {"path": "/x.py", "content": "x"})
        assert result is not None
        assert "DELEGATION CHECK" in cast("str", result.get("contextModification", ""))

    def test_fires_for_mutating_shell_command(self, mocker: MockerFixture) -> None:
        mocker.patch.dict("os.environ", {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}, clear=True)
        result = _run("execute_command", {"command": "npm run build"})
        assert result is not None
        assert "DELEGATION CHECK" in cast("str", result.get("contextModification", ""))


class TestLargeFileReadGuard:
    def test_long_file_without_range_is_blocked(self, tmp_path: Path) -> None:
        file_path = tmp_path / "long.txt"
        file_path.write_text("\n" * 1001)
        result = _run("read_file", {"path": str(file_path)})
        assert result is not None
        error = cast("str", result.get("errorMessage", ""))
        assert "1001 lines" in error
        assert "MUST search it" in error

    def test_long_file_with_bounded_range_is_allowed(self, tmp_path: Path) -> None:
        file_path = tmp_path / "long.txt"
        file_path.write_text("\n" * 1001)
        result = _run("read_file", {"path": str(file_path), "start_line": 1, "end_line": 500})
        assert result is None

    def test_short_file_without_range_is_allowed(self, tmp_path: Path) -> None:
        file_path = tmp_path / "short.txt"
        file_path.write_text("\n" * 10)
        result = _run("read_file", {"path": str(file_path)})
        assert result is None


class TestRequiredSkillGuardIntegration:
    def test_command_without_recorded_skill_is_blocked(self) -> None:
        result = _run("execute_command", {"command": "git status"})
        assert result is not None
        error = cast("str", result.get("errorMessage", ""))
        assert "git-usage" in error
        assert "skill" in error.lower()

    def test_command_with_recorded_skill_is_allowed(self) -> None:
        record_skill("task-1", "git-usage")
        result = _run("execute_command", {"command": "git status"})
        assert result is None


class TestAttemptCompletionTaskProgressGuard:
    def test_unchecked_items_block_with_count(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _init_clean_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = _run(
            "attempt_completion",
            {"task_progress": "- [ ] one\n- [x] two\n- [ ] three"},
        )
        assert result is not None
        error = cast("str", result.get("errorMessage", ""))
        assert "2 incomplete" in error

    def test_all_checked_items_is_allowed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _init_clean_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = _run("attempt_completion", {"task_progress": "- [x] one\n- [x] two"})
        assert result is None

    def test_empty_task_progress_is_allowed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _init_clean_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = _run("attempt_completion", {"task_progress": ""})
        assert result is None

    def test_absent_task_progress_is_allowed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _init_clean_repo(tmp_path)
        monkeypatch.chdir(tmp_path)
        result = _run("attempt_completion", {})
        assert result is None


class TestAttemptCompletionDirtyTreeGuard:
    def test_dirty_working_tree_blocks(self, tmp_path: Path) -> None:
        _init_clean_repo(tmp_path)
        (tmp_path / "committed.txt").write_text("modified")
        result = _run(
            "attempt_completion",
            {"task_progress": ""},
            workspace_roots=[str(tmp_path)],
        )
        assert result is not None
        assert "uncommitted changes" in cast("str", result.get("errorMessage", ""))

    def test_clean_working_tree_is_allowed(self, tmp_path: Path) -> None:
        _init_clean_repo(tmp_path)
        result = _run(
            "attempt_completion",
            {"task_progress": ""},
            workspace_roots=[str(tmp_path)],
        )
        assert result is None

    def test_non_repo_path_is_tolerated(self, tmp_path: Path) -> None:
        result = _run(
            "attempt_completion",
            {"task_progress": ""},
            workspace_roots=[str(tmp_path)],
        )
        assert result is None


class TestPreShellPluginScope:
    def test_reaches_plugin_with_documented_kwargs(self, mocker: MockerFixture) -> None:
        from cline_hooks.core.plugin import HooksPlugin
        from cline_hooks.core.vocabulary import PluginScope

        captured: list[dict[str, object]] = []

        class _CapturingPlugin(HooksPlugin):
            def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
                if hook_name == PluginScope.PRE_SHELL:
                    captured.append(kwargs)
                return None

        mocker.patch(
            "cline_hooks.handlers.pre_tool_use.load_plugins",
            return_value=[_CapturingPlugin()],
        )
        _run("execute_command", {"command": "ls -la"}, workspace_roots=["/repo"])
        assert len(captured) == 1
        kwargs = captured[0]
        assert kwargs["command"] == "ls -la"
        assert kwargs["workspace_roots"] == ["/repo"]
        assert kwargs["agent_type"] == ""

    def test_plugin_block_blocks_the_shell_call(self, mocker: MockerFixture) -> None:
        from cline_hooks.core.plugin import HookResult, HooksPlugin
        from cline_hooks.core.vocabulary import PluginScope

        class _BlockingPlugin(HooksPlugin):
            def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
                if hook_name == PluginScope.PRE_SHELL:
                    return HookResult(block="blocked by plugin")
                return None

        mocker.patch(
            "cline_hooks.handlers.pre_tool_use.load_plugins",
            return_value=[_BlockingPlugin()],
        )
        result = _run("execute_command", {"command": "ls -la"})
        assert result is not None
        assert "blocked by plugin" in cast("str", result.get("errorMessage", ""))
