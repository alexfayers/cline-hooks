from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest

from cline_hooks.frontends.cline import parse_cline_data as parse_data
from cline_hooks.handlers.pre_tool_use import (
    _is_managed_path,
    _starts_with_emoji,
    handle_pre_tool_use,
)
from cline_hooks.state.store import TaskStateStore

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputPreToolUse

_BASE = {
    "clineVersion": "1.0.0",
    "timestamp": "0",
    "taskId": "task-1",
    "userId": "user-1",
    "workspaceRoots": [],
    "hookName": "PreToolUse",
}


def _make_hook(tool_name: str, parameters: dict[str, object]) -> HookInputPreToolUse:
    return cast(
        "HookInputPreToolUse",
        parse_data(
            json.dumps({
                **_BASE,
                "preToolUse": {"toolName": tool_name, "parameters": parameters},
            })
        ),
    )


def _run(tool_name: str, parameters: dict[str, object]) -> dict[str, object] | None:
    hook = _make_hook(tool_name, parameters)
    output: list[str] = []
    try:
        with patch("builtins.print", side_effect=lambda s, **kw: output.append(s)):
            handle_pre_tool_use(hook)
    except SystemExit:
        pass
    if not output:
        return None
    return cast("dict[str, object]", json.loads(output[0]))


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
        assert "tool" in cast("str", result.get("errorMessage", ""))

    def test_grep_standalone_is_blocked(self) -> None:
        result = _run("execute_command", {"command": "grep -r foo ."})
        assert result is not None
        assert "Grep tool" in cast("str", result.get("errorMessage", ""))

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
        result = _run("execute_command", {"command": "echo hello"})
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

    def test_standalone_cat_via_bash_tool_is_blocked(self) -> None:
        result = _run("Bash", {"command": "cat /path/to/file.py"})
        assert result is not None
        assert "Read tool" in cast("str", result.get("errorMessage", ""))

    def test_bash_tool_piped_cat_is_allowed(self) -> None:
        result = _run("Bash", {"command": "cat file.json | python3 -m json.tool"})
        assert result is None


class TestBashToolCommandRules:
    def test_rm_f_blocked_via_bash_tool(self) -> None:
        result = _run("Bash", {"command": "rm -f file.txt"})
        assert result is not None
        assert "rm -f" in cast("str", result.get("errorMessage", "")).lower()

    def test_safe_command_allowed_via_bash_tool(self) -> None:
        result = _run("Bash", {"command": "ls -la"})
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
        _run("execute_command", {"command": "echo hello"})
        assert store.get_blocks("task-1") == []

    def test_no_stale_blocks_when_no_previous_blocks(self) -> None:
        store = TaskStateStore()
        _run("execute_command", {"command": "echo hello"})
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
                    "preToolUse": {"toolName": "read_file", "parameters": {"path": "/x.py"}},
                })
            ),
        )
        with (
            patch("cline_hooks.handlers.pre_tool_use.collect_hook_results", side_effect=_fake_collect),
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


class TestManagedFileWriteGuard:
    _MANAGED_FILE = "/Users/test/.claude/rules/managed-rule.md"

    @pytest.fixture(autouse=True)
    def _mock_managed_files(self) -> None:
        import cline_hooks.handlers.pre_tool_use as module

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

    def test_edit_blocked_for_managed_file(self) -> None:
        result = _run(
            "Edit",
            {
                "file_path": self._MANAGED_FILE,
                "old_string": "old",
                "new_string": "new",
            },
        )
        assert result is not None
        assert "source file" in cast("str", result.get("errorMessage", "")).lower()

    def test_edit_allowed_for_unmanaged_file_in_same_dir(self) -> None:
        result = _run(
            "Edit",
            {
                "file_path": "/Users/test/.claude/rules/my-custom-rule.md",
                "old_string": "old",
                "new_string": "new",
            },
        )
        assert result is None or "source file" not in cast("str", result.get("errorMessage", "")).lower()

    def test_write_blocked_for_managed_file(self) -> None:
        result = _run(
            "Write",
            {"file_path": self._MANAGED_FILE, "content": "# overwrite"},
        )
        assert result is not None
        assert "source file" in cast("str", result.get("errorMessage", "")).lower()

    def test_write_allowed_for_unmanaged_file(self) -> None:
        result = _run(
            "Write",
            {
                "file_path": "/some/random/safe-file.md",
                "content": "# new file",
            },
        )
        assert result is None or "source file" not in cast("str", result.get("errorMessage", "")).lower()
