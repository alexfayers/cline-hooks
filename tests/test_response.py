from __future__ import annotations

from io import StringIO
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from cline_hooks.core.outcome import Outcome
from cline_hooks.core.response import render
from cline_hooks.frontends.claude_code import ClaudeCodeProtocol
from cline_hooks.frontends.cline import ClineProtocol
from cline_hooks.frontends.kiro import KiroProtocol
from cline_hooks.frontends.pi import PiProtocol

if TYPE_CHECKING:
    from cline_hooks.core.protocol import Protocol


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
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "additionalContext": "ctx text",
            },
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
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": "trace text",
            },
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
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "ctx text",
            },
        }

    def test_allow_neither_emits_nothing(self) -> None:
        proto = ClaudeCodeProtocol()
        buf = StringIO()
        with patch("sys.stdout", buf), pytest.raises(SystemExit) as exc:
            proto.allow()
        assert exc.value.code == 0
        assert buf.getvalue() == ""


class TestRender:
    @pytest.mark.parametrize(("label", "expected"), [("", "ctx"), ("MEMORY REMINDER", "MEMORY REMINDER: ctx")])
    def test_allow_against_cline_writes_the_labelled_context(self, label: str, expected: str) -> None:
        response = render(Outcome.allow("ctx", label=label), ClineProtocol())
        assert response.exit_code == 0
        assert json.loads(response.stdout)["contextModification"] == expected

    @pytest.mark.parametrize(
        ("outcome", "protocol_cls"),
        [
            (Outcome.block("nope"), KiroProtocol),
            (Outcome.block("nope"), PiProtocol),
            (Outcome.feedback("nope"), PiProtocol),
        ],
    )
    def test_refusal_writes_stderr_with_exit_2(self, outcome: Outcome, protocol_cls: type[Protocol]) -> None:
        response = render(outcome, protocol_cls())
        assert response.exit_code == 2
        assert response.stderr == "nope"

    @pytest.mark.parametrize(
        ("outcome", "expected"), [(Outcome.allow("ctx", label="Lbl"), "Lbl: ctx"), (Outcome.allow(), "")]
    )
    def test_allow_against_pi_writes_plain_stdout(self, outcome: Outcome, expected: str) -> None:
        response = render(outcome, PiProtocol())
        assert response.exit_code == 0
        assert response.stdout == expected

    def test_feedback_outcome_against_claude_code(self) -> None:
        response = render(Outcome.feedback("trace text"), ClaudeCodeProtocol())
        assert response.exit_code == 0
        assert json.loads(response.stdout) == {
            "hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "trace text"},
        }

    def test_allow_outcome_carries_user_message_for_claude_code(self) -> None:
        response = render(Outcome.allow(user_message="user text"), ClaudeCodeProtocol("SessionStart"))
        assert response.exit_code == 0
        assert json.loads(response.stdout) == {"systemMessage": "user text"}
