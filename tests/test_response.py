from __future__ import annotations

from io import StringIO
import json
from typing import cast
from unittest.mock import patch

import pytest

from cline_hooks.frontends.cline import ClineProtocol
from cline_hooks.frontends.kiro import KiroProtocol
from cline_hooks.response import allow, block


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

    def test_block(self) -> None:
        proto = ClineProtocol()
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.block("oops")
        assert exc.value.code == 0
        result = json.loads(buf.getvalue())
        assert result == {"cancel": True, "errorMessage": "oops"}


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
        with patch("cline_hooks.state.TaskStateStore.record_block") as mock_record:
            _capture_block("reason", task_id="task-1", tool_name="execute_command")
        mock_record.assert_called_once_with("task-1", "execute_command", "reason")

    def test_no_state_store_call_without_task_id(self) -> None:
        with patch("cline_hooks.state.TaskStateStore.record_block") as mock_record:
            _capture_block("reason")
        mock_record.assert_not_called()
