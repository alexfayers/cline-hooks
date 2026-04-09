from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest

from cline_hooks.frontends.cline import parse_cline_data as parse_data
from cline_hooks.handlers.pre_tool_use import (
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

    def test_grep_standalone_is_not_blocked(self) -> None:
        result = _run("execute_command", {"command": "grep -r foo ."})
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

    def test_head_standalone_not_blocked(self) -> None:
        result = _run("execute_command", {"command": "head -n 10 file.txt"})
        assert result is None

    def test_tail_with_build_is_blocked(self) -> None:
        result = _run("execute_command", {"command": "just | tail -n 20"})
        assert result is not None
        assert "full output" in cast("str", result.get("errorMessage", ""))

    def test_tail_standalone_not_blocked(self) -> None:
        result = _run("execute_command", {"command": "tail -n 20 file.log"})
        assert result is None

    def test_tail_follow_without_build_not_blocked(self) -> None:
        result = _run("execute_command", {"command": "tail -f service.log"})
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
