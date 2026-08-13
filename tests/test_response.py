from __future__ import annotations

from io import StringIO
import json
from typing import cast
from unittest.mock import patch

import pytest

from cline_hooks.core.response import allow, block, feedback
from cline_hooks.frontends.claude_code import ClaudeCodeProtocol
from cline_hooks.frontends.cline import ClineProtocol
from cline_hooks.frontends.kiro import KiroProtocol


def _capture_allow(message: str | None = None, *, prefix: str = "REMINDER") -> dict[str, object]:
    buf = StringIO()
    with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
        allow(message, prefix=prefix)
    assert exc.value.code == 0
    return cast("dict[str, object]", json.loads(buf.getvalue()))


def _capture_block(message: str, *, task_id: str | None = None, tool_name: str | None = None) -> dict[str, object]:
    buf = StringIO()
    with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
        block(message, task_id=task_id, tool_name=tool_name)
    assert exc.value.code == 0
    return cast("dict[str, object]", json.loads(buf.getvalue()))


def _capture_feedback(message: str) -> dict[str, object]:
    buf = StringIO()
    with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
        feedback(message)
    assert exc.value.code == 0
    return cast("dict[str, object]", json.loads(buf.getvalue()))


class TestClineProtocol:
    def test_allow_no_message(self) -> None:
        proto = ClineProtocol()
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.allow()
        assert exc.value.code == 0
        assert json.loads(buf.getvalue()) == {"cancel": False}

    def test_allow_with_message(self) -> None:
        proto = ClineProtocol()
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit):
            proto.allow("ctx")
        assert json.loads(buf.getvalue())["contextModification"] == "ctx"

    def test_supports_user_message_false(self) -> None:
        assert ClineProtocol().supports_user_message() is False

    def test_allow_ignores_system_message(self) -> None:
        proto = ClineProtocol()
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.allow(system_message="user text")
        assert exc.value.code == 0
        assert json.loads(buf.getvalue()) == {"cancel": False}

    def test_block(self) -> None:
        proto = ClineProtocol()
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.block("oops")
        assert exc.value.code == 0
        result = json.loads(buf.getvalue())
        assert result == {"cancel": True, "errorMessage": "oops"}

    def test_feedback_defaults_to_block(self) -> None:
        proto = ClineProtocol()
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.feedback("oops")
        assert exc.value.code == 0
        assert json.loads(buf.getvalue()) == {"cancel": True, "errorMessage": "oops"}


class TestKiroProtocol:
    def test_allow_no_message(self) -> None:
        proto = KiroProtocol()
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.allow()
        assert exc.value.code == 0
        assert buf.getvalue() == ""

    def test_allow_with_message(self) -> None:
        proto = KiroProtocol()
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.allow("context here")
        assert exc.value.code == 0
        assert buf.getvalue() == "context here"

    def test_block(self) -> None:
        proto = KiroProtocol()
        err = StringIO()
        with patch("sys.stderr", err), pytest.raises(SystemExit) as exc:
            proto.block("bad")
        assert exc.value.code == 2
        assert err.getvalue() == "bad"

    def test_feedback_continues_via_decision_json(self) -> None:
        proto = KiroProtocol()
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.feedback("bad")
        assert exc.value.code == 0
        assert json.loads(buf.getvalue()) == {"decision": "block", "reason": "bad"}

    def test_supports_user_message_defaults_false(self) -> None:
        assert KiroProtocol().supports_user_message() is False

    def test_allow_ignores_system_message(self) -> None:
        proto = KiroProtocol()
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.allow("context here", system_message="user text")
        assert exc.value.code == 0
        assert buf.getvalue() == "context here"


class TestClaudeCodeProtocol:
    def test_allow_no_message(self) -> None:
        proto = ClaudeCodeProtocol()
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.allow()
        assert exc.value.code == 0
        assert buf.getvalue() == ""

    def test_allow_with_message_uses_additional_context_exit_0(self) -> None:
        proto = ClaudeCodeProtocol("PreToolUse")
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.allow("ctx text")
        assert exc.value.code == 0
        assert json.loads(buf.getvalue()) == {
            "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "ctx text"},
        }

    def test_allow_echoes_raw_event_name_not_remapped_name(self) -> None:
        proto = ClaudeCodeProtocol("SessionStart")
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit):
            proto.allow("ctx text")
        assert json.loads(buf.getvalue())["hookSpecificOutput"]["hookEventName"] == "SessionStart"

    def test_block_still_exits_2_with_stderr(self) -> None:
        proto = ClaudeCodeProtocol()
        err = StringIO()
        with patch("sys.stderr", err), pytest.raises(SystemExit) as exc:
            proto.block("bad")
        assert exc.value.code == 2
        assert err.getvalue() == "bad"

    def test_feedback_uses_additional_context_exit_0(self) -> None:
        proto = ClaudeCodeProtocol()
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.feedback("trace text")
        assert exc.value.code == 0
        assert json.loads(buf.getvalue()) == {
            "hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "trace text"},
        }

    def test_supports_user_message_true(self) -> None:
        assert ClaudeCodeProtocol().supports_user_message() is True

    def test_allow_system_message_only_emits_top_level(self) -> None:
        proto = ClaudeCodeProtocol("SessionStart")
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.allow(system_message="user text")
        assert exc.value.code == 0
        assert json.loads(buf.getvalue()) == {"systemMessage": "user text"}

    def test_allow_message_and_system_message_emits_both(self) -> None:
        proto = ClaudeCodeProtocol("SessionStart")
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.allow("ctx text", system_message="user text")
        assert exc.value.code == 0
        assert json.loads(buf.getvalue()) == {
            "systemMessage": "user text",
            "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "ctx text"},
        }

    def test_allow_neither_emits_nothing(self) -> None:
        proto = ClaudeCodeProtocol()
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.allow()
        assert exc.value.code == 0
        assert buf.getvalue() == ""


class TestAllow:
    def test_no_message_produces_no_context(self) -> None:
        result = _capture_allow()
        assert result == {"cancel": False}
        assert "contextModification" not in result

    def test_message_uses_default_prefix(self) -> None:
        result = _capture_allow("do something")
        assert result["contextModification"] == "REMINDER: do something"

    def test_custom_prefix(self) -> None:
        result = _capture_allow("update memory", prefix="MEMORY REMINDER")
        assert result["contextModification"] == "MEMORY REMINDER: update memory"

    def test_not_cancelled(self) -> None:
        result = _capture_allow("msg")
        assert result["cancel"] is False


class TestBlock:
    def test_cancels(self) -> None:
        result = _capture_block("bad command")
        assert result["cancel"] is True

    def test_error_message_included(self) -> None:
        result = _capture_block("bad command")
        assert result["errorMessage"] == "bad command"

    def test_records_block_event_when_task_and_tool_given(self) -> None:
        with patch("cline_hooks.state.store.TaskStateStore.record_block") as mock_record:
            _capture_block("reason", task_id="task-1", tool_name="execute_command")
        mock_record.assert_called_once_with("task-1", "execute_command", "reason")

    def test_no_state_store_call_without_task_id(self) -> None:
        with patch("cline_hooks.state.store.TaskStateStore.record_block") as mock_record:
            _capture_block("reason")
        mock_record.assert_not_called()


class TestFeedback:
    def test_continues_with_block_shaped_output_under_default_protocol(self) -> None:
        result = _capture_feedback("trace text")
        assert result == {"cancel": True, "errorMessage": "trace text"}

    def test_never_records_block_event(self) -> None:
        with patch("cline_hooks.state.store.TaskStateStore.record_block") as mock_record:
            _capture_feedback("trace text")
        mock_record.assert_not_called()
