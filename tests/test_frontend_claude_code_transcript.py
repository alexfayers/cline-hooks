from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from cline_hooks.frontends.claude_code.transcript import _TEAMMATE_PROBE_LINES, ClaudeCodeTranscriptReader

_reader = ClaudeCodeTranscriptReader()
get_context_tokens = _reader.context_tokens
get_turn_assistant_text = _reader.turn_assistant_text
get_subagent_context_tokens = _reader.subagent_context_tokens
get_subagent_report = _reader.subagent_report

if TYPE_CHECKING:
    from pathlib import Path


def _user(content: str | list[dict[str, Any]] = "hello", *, sidechain: bool = False) -> dict[str, Any]:
    return {
        "type": "user",
        "isSidechain": sidechain,
        "message": {"role": "user", "content": content},
    }


def _assistant_text(text: str, *, sidechain: bool = False) -> dict[str, Any]:
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


def _assistant_tool_use(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "assistant",
        "isSidechain": True,
        "message": {"role": "assistant", "content": [{"type": "tool_use", "name": name, "input": tool_input}]},
    }


def _tool_result(result: str = "ok") -> dict[str, Any]:
    return {
        "type": "user",
        "isSidechain": False,
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "content": result}],
        },
    }


def _assistant(
    *,
    input_tokens: int = 0,
    cache_read: int = 0,
    cache_creation: int = 0,
    sidechain: bool = False,
) -> dict[str, Any]:
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {
            "role": "assistant",
            "usage": {
                "input_tokens": input_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
            },
        },
    }


def _assistant_with_iterations(
    *, top_cache_read: int, iterations: list[dict[str, Any]], sidechain: bool = False
) -> dict[str, Any]:
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {
            "role": "assistant",
            "usage": {
                "input_tokens": 4,
                "cache_read_input_tokens": top_cache_read,
                "cache_creation_input_tokens": 1596,
                "iterations": iterations,
            },
        },
    }


def _write_jsonl(path: Path, entries: list[dict[str, Any]]) -> str:
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    return str(path)


class TestGetContextTokens:
    def test_sums_last_assistant_usage(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [_assistant(input_tokens=10, cache_read=200, cache_creation=5)],
        )
        assert get_context_tokens(path) == 215

    def test_picks_last_assistant_entry(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [
                _assistant(cache_read=500),
                _assistant(input_tokens=1, cache_read=300),
            ],
        )
        assert get_context_tokens(path) == 301

    def test_ignores_sidechain_assistant_entries(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [
                _assistant(cache_read=100),
                _assistant(cache_read=999, sidechain=True),
            ],
        )
        assert get_context_tokens(path) == 100

    def test_ignores_non_assistant_lines(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [
                _assistant(cache_read=100),
                {
                    "type": "user",
                    "message": {"role": "user", "usage": {"input_tokens": 9}},
                },
                {"type": "system", "message": {}},
            ],
        )
        assert get_context_tokens(path) == 100

    def test_missing_usage_keys_default_to_zero(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text(
            json.dumps({
                "type": "assistant",
                "isSidechain": False,
                "message": {
                    "role": "assistant",
                    "usage": {"cache_read_input_tokens": 50},
                },
            }),
            encoding="utf-8",
        )
        assert get_context_tokens(str(path)) == 50

    def test_nonexistent_path_returns_none(self, tmp_path: Path) -> None:
        assert get_context_tokens(str(tmp_path / "missing.jsonl")) is None

    def test_malformed_line_is_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text("not json\n" + json.dumps(_assistant(cache_read=42)), encoding="utf-8")
        assert get_context_tokens(str(path)) == 42

    def test_empty_file_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text("", encoding="utf-8")
        assert get_context_tokens(str(path)) is None

    def test_server_tool_rollup_uses_last_message_iteration(self, tmp_path: Path) -> None:
        """A rolled-up server-tool usage reports the last message iteration.

        A turn that calls a server-side tool (e.g. advisor) reports a usage
        rolled up across sub-calls; the real context is the last `message`
        iteration, not the inflated top-level sum.
        """
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [
                _assistant(cache_read=168_000),
                _assistant_with_iterations(
                    top_cache_read=337_550,
                    iterations=[
                        {
                            "type": "message",
                            "input_tokens": 2,
                            "cache_read_input_tokens": 168_532,
                            "cache_creation_input_tokens": 486,
                        },
                        {
                            "type": "advisor_message",
                            "input_tokens": 170_530,
                            "cache_read_input_tokens": 0,
                            "cache_creation_input_tokens": 0,
                        },
                        {
                            "type": "message",
                            "input_tokens": 2,
                            "cache_read_input_tokens": 169_018,
                            "cache_creation_input_tokens": 1_110,
                        },
                    ],
                ),
            ],
        )
        assert get_context_tokens(path) == 169_018 + 1_110 + 2

    def test_rollup_without_messages_uses_top_level(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [
                _assistant_with_iterations(
                    top_cache_read=5_000,
                    iterations=[
                        {
                            "type": "advisor_message",
                            "input_tokens": 1,
                            "cache_read_input_tokens": 0,
                            "cache_creation_input_tokens": 0,
                        },
                    ],
                ),
            ],
        )
        assert get_context_tokens(path) == 4 + 5_000 + 1596

    def test_no_assistant_with_usage_returns_none(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [{"type": "user", "message": {"role": "user"}}],
        )
        assert get_context_tokens(path) is None


class TestGetSubagentContextTokens:
    def test_reads_last_usage_from_the_subagent_transcript_file(self, tmp_path: Path) -> None:
        session_dir = tmp_path / "session"
        subagents_dir = session_dir / "subagents"
        subagents_dir.mkdir(parents=True)
        _write_jsonl(
            subagents_dir / "agent-sub1.jsonl",
            [
                _assistant(cache_read=50, sidechain=True),
                _assistant(input_tokens=5, cache_read=120, sidechain=True),
            ],
        )
        transcript_path = str(session_dir) + ".jsonl"
        assert get_subagent_context_tokens(transcript_path, "sub1") == 125

    def test_missing_subagent_file_returns_none(self, tmp_path: Path) -> None:
        transcript_path = str(tmp_path / "session.jsonl")
        assert get_subagent_context_tokens(transcript_path, "sub1") is None


class TestIsTeammate:
    def test_true_when_first_message_entry_names_team_and_agent(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [
                {**_user(), "teamName": "session-team01", "agentName": "probe"},
                _assistant_text("hi"),
            ],
        )
        assert _reader.is_teammate(path) is True

    def test_true_when_non_message_and_malformed_lines_precede_the_entry(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text(
            '{"type": "summary"}\nnot json\n'
            + json.dumps({**_user(), "teamName": "session-team01", "agentName": "probe"}),
            encoding="utf-8",
        )
        assert _reader.is_teammate(str(path)) is True

    def test_false_for_lead_style_transcript(self, tmp_path: Path) -> None:
        path = _write_jsonl(tmp_path / "t.jsonl", [_user(), _assistant_text("hi")])
        assert _reader.is_teammate(path) is False

    def test_false_for_missing_file(self, tmp_path: Path) -> None:
        assert _reader.is_teammate(str(tmp_path / "missing.jsonl")) is False

    def test_false_when_fields_appear_only_beyond_the_probe_cap(self, tmp_path: Path) -> None:
        filler = [{"type": "summary"}] * _TEAMMATE_PROBE_LINES
        path = _write_jsonl(
            tmp_path / "t.jsonl", [*filler, {**_user(), "teamName": "session-team01", "agentName": "probe"}]
        )
        assert _reader.is_teammate(path) is False


class TestGetTurnAssistantText:
    def test_joins_all_assistant_text_since_last_user_prompt(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [_user(), _assistant_text("first"), _assistant_text("second")],
        )
        assert get_turn_assistant_text(path) == "first\nsecond"

    def test_ignores_text_before_last_user_prompt(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [_user(), _assistant_text("old"), _user("next"), _assistant_text("new")],
        )
        assert get_turn_assistant_text(path) == "new"

    def test_tool_result_entries_are_not_turn_boundaries(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [
                _user(),
                _assistant_text("first"),
                _tool_result(),
                _assistant_text("second"),
            ],
        )
        assert get_turn_assistant_text(path) == "first\nsecond"

    def test_ignores_sidechain_assistant_entries(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [_user(), _assistant_text("main"), _assistant_text("sub", sidechain=True)],
        )
        assert get_turn_assistant_text(path) == "main"

    def test_no_user_prompt_scans_from_start(self, tmp_path: Path) -> None:
        path = _write_jsonl(tmp_path / "t.jsonl", [_assistant_text("only")])
        assert get_turn_assistant_text(path) == "only"

    def test_nonexistent_path_returns_empty(self, tmp_path: Path) -> None:
        assert get_turn_assistant_text(str(tmp_path / "missing.jsonl")) == ""

    def test_empty_file_returns_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text("", encoding="utf-8")
        assert get_turn_assistant_text(str(path)) == ""

    def test_malformed_line_is_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text("not json\n" + json.dumps(_assistant_text("kept")), encoding="utf-8")
        assert get_turn_assistant_text(str(path)) == "kept"


class TestGetSubagentReport:
    def _subagent_transcript(self, tmp_path: Path, entries: list[dict[str, Any]]) -> str:
        subagents_dir = tmp_path / "session" / "subagents"
        subagents_dir.mkdir(parents=True)
        _write_jsonl(subagents_dir / "agent-sub1.jsonl", entries)
        return str(tmp_path / "session.jsonl")

    def test_returns_the_last_handback_message(self, tmp_path: Path) -> None:
        transcript_path = self._subagent_transcript(
            tmp_path,
            [
                _assistant_tool_use("SubagentHandback", {"message": "draft"}),
                _assistant_tool_use("SubagentHandback", {"message": "final report"}),
            ],
        )
        assert get_subagent_report(transcript_path, "sub1") == "final report"

    def test_falls_back_to_the_last_send_message(self, tmp_path: Path) -> None:
        transcript_path = self._subagent_transcript(
            tmp_path,
            [
                _assistant_tool_use("SendMessage", {"message": "first"}),
                _assistant_tool_use("SendMessage", {"message": "second"}),
            ],
        )
        assert get_subagent_report(transcript_path, "sub1") == "second"

    def test_handback_wins_over_a_later_send_message(self, tmp_path: Path) -> None:
        transcript_path = self._subagent_transcript(
            tmp_path,
            [
                _assistant_tool_use("SubagentHandback", {"message": "report"}),
                _assistant_tool_use("SendMessage", {"message": "chatter"}),
            ],
        )
        assert get_subagent_report(transcript_path, "sub1") == "report"

    def test_non_string_message_is_ignored(self, tmp_path: Path) -> None:
        transcript_path = self._subagent_transcript(
            tmp_path,
            [_assistant_tool_use("SendMessage", {"message": {"type": "shutdown_request"}})],
        )
        assert get_subagent_report(transcript_path, "sub1") == ""

    def test_transcript_already_under_subagents_resolves_its_siblings(self, tmp_path: Path) -> None:
        self._subagent_transcript(tmp_path, [_assistant_tool_use("SubagentHandback", {"message": "sibling report"})])
        own_path = str(tmp_path / "session" / "subagents" / "agent-other.jsonl")
        assert get_subagent_report(own_path, "sub1") == "sibling report"

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert get_subagent_report(str(tmp_path / "session.jsonl"), "sub1") == ""

    def test_malformed_line_is_skipped(self, tmp_path: Path) -> None:
        transcript_path = self._subagent_transcript(tmp_path, [])
        subagent_file = tmp_path / "session" / "subagents" / "agent-sub1.jsonl"
        subagent_file.write_text(
            "not json\n" + json.dumps(_assistant_tool_use("SubagentHandback", {"message": "kept"})),
            encoding="utf-8",
        )
        assert get_subagent_report(transcript_path, "sub1") == "kept"
