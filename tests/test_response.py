from __future__ import annotations

import json
from io import StringIO
from typing import cast
from unittest.mock import patch

import pytest

from cline_hooks.response import allow, block, respond


def _capture_respond(**kwargs: object) -> dict[str, object]:
    buf = StringIO()
    with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
        respond(**kwargs)  # type: ignore[arg-type]
    assert exc.value.code == 0
    return cast(dict[str, object], json.loads(buf.getvalue()))


def _capture_allow(
    message: str | None = None, *, prefix: str = "REMINDER"
) -> dict[str, object]:
    buf = StringIO()
    with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
        allow(message, prefix=prefix)
    assert exc.value.code == 0
    return cast(dict[str, object], json.loads(buf.getvalue()))


def _capture_block(
    message: str, *, task_id: str | None = None, tool_name: str | None = None
) -> dict[str, object]:
    buf = StringIO()
    with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
        block(message, task_id=task_id, tool_name=tool_name)
    assert exc.value.code == 0
    return cast(dict[str, object], json.loads(buf.getvalue()))


class TestRespond:
    def test_allow_no_message(self) -> None:
        result = _capture_respond(cancel=False)
        assert result == {"cancel": False}

    def test_cancel_with_error(self) -> None:
        result = _capture_respond(cancel=True, error_message="oops")
        assert result == {"cancel": True, "errorMessage": "oops"}

    def test_context_modification_included(self) -> None:
        result = _capture_respond(cancel=False, context_modification="ctx")
        assert result["contextModification"] == "ctx"

    def test_exits_zero(self) -> None:
        with patch("sys.stdout", StringIO()), pytest.raises(SystemExit) as exc:
            respond(cancel=False)
        assert exc.value.code == 0


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
