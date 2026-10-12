from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from cline_hooks.frontends.pi.protocol import PiProtocol
from cline_hooks.frontends.pi.transcript import PiTranscriptReader

if TYPE_CHECKING:
    from pathlib import Path
_reader = PiTranscriptReader()


def _message(
    entry_id: str,
    parent_id: str | None,
    role: str,
    *,
    text: str = "",
    total_tokens: int | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {"role": role, "content": [{"type": "text", "text": text}]}
    if role == "assistant":
        message["stopReason"] = "stop"
        if total_tokens is not None:
            message["usage"] = {"input": 1, "output": 1, "cacheRead": 0, "cacheWrite": 0, "totalTokens": total_tokens}
    return {"type": "message", "id": entry_id, "parentId": parent_id, "message": message}


def _write(tmp_path: Path, *entries: dict[str, Any]) -> str:
    path = tmp_path / "session.jsonl"
    header = {"type": "session", "version": 3, "id": "fixture", "cwd": "/home/user/project"}
    path.write_text("\n".join(json.dumps(line) for line in [header, *entries]) + "\n", encoding="utf-8")
    return str(path)


class TestContextTokens:
    def test_is_reported_by_the_bridge_not_the_transcript(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _message("1", None, "user"), _message("2", "1", "assistant", total_tokens=77))
        assert _reader.context_tokens(path) is None
        assert _reader.subagent_context_tokens(path, "agent-1") is None


class TestTurnAssistantText:
    def test_joins_assistant_text_since_the_last_user_prompt(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            _message("1", None, "user", text="first"),
            _message("2", "1", "assistant", text="old"),
            _message("3", "2", "user", text="second"),
            _message("4", "3", "assistant", text="alpha"),
            _message("5", "4", "toolResult", text="tool output"),
            _message("6", "5", "assistant", text="beta"),
        )
        assert _reader.turn_assistant_text(path) == "alpha\nbeta"

    def test_ignores_an_abandoned_branch(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path,
            _message("1", None, "user", text="q"),
            _message("2", "1", "assistant", text="abandoned"),
            _message("3", "1", "assistant", text="kept"),
        )
        assert _reader.turn_assistant_text(path) == "kept"

    def test_is_empty_for_a_missing_file(self, tmp_path: Path) -> None:
        assert _reader.turn_assistant_text(str(tmp_path / "absent.jsonl")) == ""


class TestDefaults:
    def test_pi_protocol_uses_the_pi_reader(self) -> None:
        assert isinstance(PiProtocol.transcript, PiTranscriptReader)

    def test_is_not_a_teammate_and_has_no_subagent_report(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _message("1", None, "user"))
        assert _reader.is_teammate(path) is False
        assert _reader.subagent_report(path, "agent-1") == ""
