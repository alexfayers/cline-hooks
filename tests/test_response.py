from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.outcome import Outcome
from cline_hooks.core.response import render
from cline_hooks.frontends.claude_code import ClaudeCodeProtocol
from cline_hooks.frontends.cline import ClineProtocol
from cline_hooks.frontends.codex import CodexProtocol
from cline_hooks.frontends.kiro import KiroProtocol
from cline_hooks.frontends.pi import PiProtocol

if TYPE_CHECKING:
    from cline_hooks.core.protocol import Protocol


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
            (Outcome.block("nope"), ClaudeCodeProtocol),
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

    def test_feedback_against_cline_cancels(self) -> None:
        response = render(Outcome.feedback("nope"), ClineProtocol())
        assert json.loads(response.stdout) == {"cancel": True, "errorMessage": "nope"}

    def test_feedback_against_kiro_writes_the_stop_decision_json(self) -> None:
        response = render(Outcome.feedback("nope"), KiroProtocol())
        assert response.exit_code == 0
        assert json.loads(response.stdout) == {"decision": "block", "reason": "nope"}

    def test_allow_against_claude_code_echoes_the_raw_event_name(self) -> None:
        response = render(Outcome.allow("ctx"), ClaudeCodeProtocol("SessionStart"))
        assert json.loads(response.stdout)["hookSpecificOutput"]["hookEventName"] == "SessionStart"

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


class TestRenderCodex:
    @pytest.mark.parametrize("event", ["Stop", "SubagentStop"])
    def test_feedback_on_a_stop_event_exits_2_with_stderr(self, event: str) -> None:
        response = render(Outcome.feedback("trace text"), CodexProtocol(event))
        assert response.exit_code == 2
        assert response.stderr == "trace text"

    def test_updated_input_is_dropped(self) -> None:
        outcome = Outcome.allow("ctx", updated_input={"prompt": "new"}, fallback_note="try this")
        assert json.loads(render(outcome, CodexProtocol("PreToolUse")).stdout) == {
            "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "ctx\n\ntry this"},
        }


class TestRenderInputUpdate:
    def test_a_protocol_that_cannot_update_input_shows_the_fallback_note(self) -> None:
        outcome = Outcome.allow("ctx", updated_input={"task": "new"}, fallback_note="try this")
        assert json.loads(render(outcome, ClineProtocol()).stdout)["contextModification"] == "ctx\n\ntry this"

    def test_claude_code_sends_the_updated_input_without_the_fallback_note(self) -> None:
        outcome = Outcome.allow("ctx", label="REMINDER", updated_input={"prompt": "new"}, fallback_note="try this")
        assert json.loads(render(outcome, ClaudeCodeProtocol("PreToolUse")).stdout) == {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "updatedInput": {"prompt": "new"},
                "additionalContext": "REMINDER: ctx",
            },
        }

    def test_claude_code_sends_only_the_updated_input_when_there_is_no_context(self) -> None:
        outcome = Outcome.allow(updated_input={"prompt": "new"}, fallback_note="try this")
        assert json.loads(render(outcome, ClaudeCodeProtocol("PreToolUse")).stdout) == {
            "hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": {"prompt": "new"}},
        }

    def test_pi_sends_the_updated_input_and_context_as_json(self) -> None:
        outcome = Outcome.allow("ctx", label="REMINDER", updated_input={"task": "new"}, fallback_note="try this")
        assert json.loads(render(outcome, PiProtocol()).stdout) == {
            "updated_input": {"task": "new"},
            "message": "REMINDER: ctx",
        }

    def test_feedback_ignores_the_updated_input(self) -> None:
        outcome = Outcome.feedback("trace").merge(Outcome.allow(updated_input={"task": "new"}))
        assert json.loads(render(outcome, ClineProtocol()).stdout) == {"cancel": True, "errorMessage": "trace"}
