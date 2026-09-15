from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

import pytest

from cline_hooks.core.protocol import RawPayload
from cline_hooks.core.vocabulary import CanonicalHook
from cline_hooks.frontends.antigravity import AntigravityProtocol
from cline_hooks.frontends.antigravity.transcript import AntigravityTranscriptReader

if TYPE_CHECKING:
    from collections.abc import Callable

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fixture(canonical_hook: str) -> dict[str, Any]:
    """Load one Antigravity fixture payload.

    Returns:
        The parsed fixture data.
    """
    path = FIXTURES_DIR / canonical_hook / "antigravity.json"
    return dict(json.loads(path.read_text()))


def _payload(data: dict[str, Any]) -> RawPayload:
    """Wrap payload data as a raw hook invocation.

    Returns:
        A RawPayload carrying the given data.
    """
    return RawPayload(raw=json.dumps(data), data=data, env={})


def _emit(
    capsys: pytest.CaptureFixture[str],
    respond: Callable[..., NoReturn],
    *args: str,
) -> dict[str, Any]:
    """Run one of a protocol's output methods and return the response it printed.

    Returns:
        The parsed JSON response, having asserted the hook exited 0.
    """
    with pytest.raises(SystemExit) as excinfo:
        respond(*args)
    assert excinfo.value.code == 0
    return dict(json.loads(capsys.readouterr().out))


def _transcript(tmp_path: Path, *entries: dict[str, Any]) -> str:
    """Write a JSONL transcript and return its path.

    Returns:
        The path to the written transcript.
    """
    path = tmp_path / "transcript.jsonl"
    path.write_text(
        "".join(f"{json.dumps(entry)}\n" for entry in entries), encoding="utf-8"
    )
    return str(path)


class TestEventInference:
    """A payload names no event, so each is inferred from its own fields."""

    @pytest.mark.parametrize("canonical_hook", ["PreToolUse", "PostToolUse", "Stop"])
    def test_each_fixture_infers_its_own_event(self, canonical_hook: str) -> None:
        assert (
            AntigravityProtocol.infer_hook_event(_fixture(canonical_hook))
            == canonical_hook
        )

    def test_a_reported_error_marks_a_tool_call_as_finished(self) -> None:
        data = {**_fixture("PreToolUse"), "error": "exit status 1"}
        assert AntigravityProtocol.infer_hook_event(data) == CanonicalHook.POST_TOOL_USE

    def test_a_stop_is_a_stop_even_carrying_an_error(self) -> None:
        data = {**_fixture("Stop"), "error": "boom"}
        assert AntigravityProtocol.infer_hook_event(data) == CanonicalHook.STOP

    def test_an_event_with_no_identifying_field_is_not_inferred(self) -> None:
        data = {**_fixture("Stop")}
        del data["fullyIdle"]
        del data["executionNum"]
        del data["terminationReason"]
        del data["error"]
        data.update({"invocationNum": 3, "initialNumSteps": 10})
        assert AntigravityProtocol.infer_hook_event(data) == ""

    def test_an_uninferred_event_is_one_the_frontend_does_not_fire(self) -> None:
        assert AntigravityProtocol.fires("") is False


class TestDetection:
    @pytest.mark.parametrize("canonical_hook", ["PreToolUse", "PostToolUse", "Stop"])
    def test_claims_its_own_payloads(self, canonical_hook: str) -> None:
        assert AntigravityProtocol.detect(_payload(_fixture(canonical_hook))) is True

    def test_rejects_a_payload_missing_an_envelope_key(self) -> None:
        data = _fixture("PreToolUse")
        del data["artifactDirectoryPath"]
        assert AntigravityProtocol.detect(_payload(data)) is False

    def test_rejects_unparseable_input(self) -> None:
        payload = RawPayload(raw="not json", data=None, env={})
        assert AntigravityProtocol.detect(payload) is False


class TestOutput:
    def test_pre_tool_use_allow(self, capsys: pytest.CaptureFixture[str]) -> None:
        protocol = AntigravityProtocol(CanonicalHook.PRE_TOOL_USE)
        assert _emit(capsys, protocol.allow) == {"decision": "allow"}

    def test_pre_tool_use_allow_carries_context_as_a_reason(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol = AntigravityProtocol(CanonicalHook.PRE_TOOL_USE)
        assert _emit(capsys, protocol.allow, "a note") == {
            "decision": "allow",
            "reason": "a note",
        }

    def test_pre_tool_use_block_denies(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol = AntigravityProtocol(CanonicalHook.PRE_TOOL_USE)
        assert _emit(capsys, protocol.block, "no") == {
            "decision": "deny",
            "reason": "no",
        }

    def test_post_tool_use_answers_with_an_empty_object(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol = AntigravityProtocol(CanonicalHook.POST_TOOL_USE)
        assert _emit(capsys, protocol.allow, "a note") == {}
        assert _emit(capsys, protocol.block, "no") == {}

    def test_stop_allow_lets_the_loop_end(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol = AntigravityProtocol(CanonicalHook.STOP)
        assert _emit(capsys, protocol.allow) == {"decision": "allow"}

    def test_stop_feedback_re_enters_the_loop(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        protocol = AntigravityProtocol(CanonicalHook.STOP)
        assert _emit(capsys, protocol.feedback, "keep going") == {
            "decision": "continue",
            "reason": "keep going",
        }


class TestTranscriptReader:
    def test_reports_no_token_count(self, tmp_path: Path) -> None:
        reader = AntigravityTranscriptReader()
        path = _transcript(tmp_path, {"source": "MODEL", "content": "hello"})
        assert reader.context_tokens(path) is None

    def test_returns_model_text_since_the_last_user_message(
        self, tmp_path: Path
    ) -> None:
        path = _transcript(
            tmp_path,
            {"source": "MODEL", "content": "an earlier turn"},
            {"source": "USER_EXPLICIT", "content": "do the thing"},
            {"source": "SYSTEM", "content": "a system note"},
            {"source": "MODEL", "content": "first"},
            {"source": "MODEL", "content": "second"},
        )
        assert (
            AntigravityTranscriptReader().turn_assistant_text(path) == "first\nsecond"
        )

    def test_skips_a_line_that_is_not_a_json_object(self, tmp_path: Path) -> None:
        path = tmp_path / "transcript.jsonl"
        path.write_text(
            'not json\n[1, 2]\n{"source": "MODEL", "content": "kept"}\n',
            encoding="utf-8",
        )
        assert AntigravityTranscriptReader().turn_assistant_text(str(path)) == "kept"

    def test_expands_a_home_relative_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        _transcript(tmp_path, {"source": "MODEL", "content": "expanded"})
        assert (
            AntigravityTranscriptReader().turn_assistant_text("~/transcript.jsonl")
            == "expanded"
        )

    def test_unreadable_transcript_is_empty(self, tmp_path: Path) -> None:
        reader = AntigravityTranscriptReader()
        assert reader.turn_assistant_text(str(tmp_path / "missing.jsonl")) == ""
        assert reader.turn_assistant_text("") == ""
