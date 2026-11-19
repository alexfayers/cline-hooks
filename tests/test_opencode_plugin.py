from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

import pytest

HARNESS = Path(__file__).parent / "opencode_plugin_harness.mjs"
TEMPLATE = Path(__file__).parents[1] / "src" / "cline_hooks" / "frontends" / "opencode" / "plugin.ts"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _run(tmp_path: Path, cases: str, steps: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run the plugin through the harness against a fake cline-hook answering per `cases`.

    Returns:
        The harness output and every payload the fake cline-hook received.
    """
    log = tmp_path / "payloads.jsonl"
    binary = tmp_path / "cline-hook"
    binary.write_text(
        f'#!/bin/sh\ninput="$(cat)"\nprintf \'%s\\n\' "$input" >> {log}\ncase "$input" in {cases} esac\n',
        encoding="utf-8",
    )
    binary.chmod(0o755)
    script = tmp_path / "cline-hooks.ts"
    script.write_text(TEMPLATE.read_text(encoding="utf-8").replace("__CLINE_HOOK_BINARY__", str(binary)))
    steps_file = tmp_path / "steps.json"
    steps_file.write_text(json.dumps(steps), encoding="utf-8")
    completed = subprocess.run(
        ["node", str(HARNESS), str(script), str(steps_file)],  # ruff: ignore[start-process-with-partial-path]
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    payloads = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return json.loads(completed.stdout), payloads


def _message(session: str = "main", text: str = "hi") -> dict[str, Any]:
    return {
        "hook": "chat.message",
        "input": {"sessionID": session, "agent": "build"},
        "output": {"message": {"id": "msg_1"}, "parts": [{"type": "text", "text": text}]},
    }


def _tool(hook: str, tool: str = "bash", call: str = "c1", session: str = "main") -> dict[str, Any]:
    if hook == "tool.execute.before":
        return {
            "hook": hook,
            "input": {"tool": tool, "sessionID": session, "callID": call},
            "output": {"args": {"command": "ls"}},
        }
    return {
        "hook": hook,
        "input": {"tool": tool, "sessionID": session, "callID": call, "args": {"command": "ls"}},
        "output": {"title": "", "output": "done", "metadata": {}},
    }


def _idle(session: str = "main") -> dict[str, Any]:
    return {"hook": "event", "input": {"event": {"type": "session.idle", "properties": {"sessionID": session}}}}


class TestOpencodePlugin:
    def test_first_message_adds_session_and_prompt_context(self, tmp_path: Path) -> None:
        cases = "*session.created*) printf start;; *chat.message*) printf prompt;;"
        out, payloads = _run(tmp_path, cases, [_message(), _message(text="again")])

        first, second = out["results"]
        assert [part["text"] for part in first["parts"]] == ["hi", "start", "prompt"]
        assert all(part["id"].startswith("prt_") and part["synthetic"] for part in first["parts"][1:])
        assert [part["text"] for part in second["parts"]] == ["again", "prompt"]
        assert [p["hook_event_name"] for p in payloads] == ["session.created", "chat.message", "chat.message"]
        assert payloads[1] | {"prompt": "hi", "session_id": "main", "cwd": "/work/project"} == payloads[1]

    def test_blocked_tool_call_throws(self, tmp_path: Path) -> None:
        cases = "*tool.execute.before*) printf nope >&2; exit 2;;"
        out, _ = _run(tmp_path, cases, [_tool("tool.execute.before")])
        assert out["results"] == [{"error": "nope"}]

    def test_updated_input_replaces_the_args(self, tmp_path: Path) -> None:
        reply = json.dumps({"updated_input": {"command": "ls -a"}, "message": None})
        cases = f"*tool.execute.before*) printf '%s' '{reply}';;"
        out, _ = _run(tmp_path, cases, [_tool("tool.execute.before")])
        assert out["results"] == [{"args": {"command": "ls -a"}}]

    def test_notes_are_appended_to_the_tool_output(self, tmp_path: Path) -> None:
        cases = "*tool.execute.before*) printf before;; *tool.execute.after*) printf after;;"
        out, payloads = _run(tmp_path, cases, [_tool("tool.execute.before"), _tool("tool.execute.after")])
        assert out["results"][1]["output"] == "done\n\nbefore\n\nafter"
        assert payloads[1]["tool_response"] == {"success": True, "result": "done"}

    def test_mcp_tools_are_renamed(self, tmp_path: Path) -> None:
        _, payloads = _run(tmp_path, "", [_tool("tool.execute.before", tool="my_memory_read_graph")])
        assert payloads[0]["tool_name"] == "mcp__my.memory__read_graph"

    def test_child_sessions_carry_their_agent_identity(self, tmp_path: Path) -> None:
        steps = [{**_message(session="child-1"), "input": {"sessionID": "child-1", "agent": "explore"}}]
        steps.append(_tool("tool.execute.before", session="child-1"))
        _, payloads = _run(tmp_path, "", steps)
        assert payloads[-1]["agent_id"] == "child-1"
        assert payloads[-1]["agent_type"] == "explore"

    def test_blocked_stop_prompts_once_then_reports_the_stop_hook_active(self, tmp_path: Path) -> None:
        cases = "*session.idle*) printf 'keep going' >&2; exit 2;;"
        out, payloads = _run(tmp_path, cases, [_idle(), _message(text="keep going"), _idle(), _idle("child-1")])

        assert out["prompts"] == [{"id": "main", "text": "keep going"}, {"id": "main", "text": "keep going"}]
        stops = [p["stop_hook_active"] for p in payloads if p["hook_event_name"] == "session.idle"]
        assert stops == [False, True]
        assert [p["hook_event_name"] for p in payloads].count("chat.message") == 0

    def test_compaction_context_is_added(self, tmp_path: Path) -> None:
        cases = "*experimental.session.compacting*) printf recap;;"
        step = {"hook": "experimental.session.compacting", "input": {"sessionID": "main"}, "output": {"context": []}}
        out, _ = _run(tmp_path, cases, [step])
        assert out["results"] == [{"context": ["recap"]}]
