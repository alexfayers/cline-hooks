from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

import pytest

from cline_hooks.frontends.opencode import OpencodeProtocol

HARNESS = Path(__file__).parent / "opencode_plugin_harness.mjs"
TEMPLATE = Path(__file__).parents[1] / "src" / "cline_hooks" / "frontends" / "opencode" / "plugin.ts"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _run(tmp_path: Path, cases: str, steps: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run the plugin through the harness against a fake cline-hook answering per `cases`.

    Returns:
        The harness output and every payload the fake cline-hook received, with the directory it ran in.
    """
    log = tmp_path / "payloads.jsonl"
    binary = tmp_path / "cline-hook"
    binary.write_text(
        f'#!/bin/sh\ninput="$(cat)"\nprintf \'%s\\t%s\\n\' "$PWD" "$input" >> {log}\ncase "$input" in {cases} esac\n',
        encoding="utf-8",
    )
    binary.chmod(0o755)
    for directory in ("project", "other"):
        (tmp_path / directory).mkdir()
    script = tmp_path / "cline-hooks.ts"
    script.write_text(TEMPLATE.read_text(encoding="utf-8").replace("__CLINE_HOOK_BINARY__", str(binary)))
    steps_file = tmp_path / "steps.json"
    steps_file.write_text(json.dumps(steps), encoding="utf-8")
    completed = subprocess.run(
        ["node", str(HARNESS), str(script), str(steps_file), str(tmp_path)],  # ruff: ignore[start-process-with-partial-path]
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    payloads = []
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            ran_in, payload = line.split("\t", 1)
            payloads.append({**json.loads(payload), "ran_in": ran_in})
    return json.loads(completed.stdout), payloads


def _prompt(session: str = "main", text: str = "hi") -> dict[str, Any]:
    return {"hook": "session.prompt", "event": {"sessionID": session, "prompt": {"text": text}}}


def _before(
    tool: str = "shell", call: str = "c1", session: str = "main", as_agent: str = "build", **tool_input: Any
) -> dict[str, Any]:
    event = {
        "tool": tool,
        "sessionID": session,
        "agent": as_agent,
        "id": call,
        "input": tool_input or {"command": "ls"},
    }
    return {"hook": "tool.execute.before", "event": event}


def _after(tool: str = "shell", call: str = "c1", session: str = "main", **tool_input: Any) -> dict[str, Any]:
    event = {
        "tool": tool,
        "sessionID": session,
        "agent": "build",
        "id": call,
        "input": tool_input or {"command": "ls"},
        "status": "completed",
        "result": {"output": {"exitCode": 0}, "content": [{"type": "text", "text": "done"}]},
    }
    return {"hook": "tool.execute.after", "event": event}


def _idle(session: str = "main", background: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"hook": "session.experimental.idle", "event": {"sessionID": session, "background": background or []}}


class TestOpencodePlugin:
    def test_default_exports_a_v2_plugin_with_every_hook(self, tmp_path: Path) -> None:
        out, _ = _run(tmp_path, "", [])
        assert out["id"] == "cline-hooks"
        assert sorted(out["registered"]) == [
            "session.compaction",
            "session.experimental.idle",
            "session.prompt",
            "tool.execute.after",
            "tool.execute.before",
        ]

    def test_sends_every_registered_hook_name(self) -> None:
        content = TEMPLATE.read_text(encoding="utf-8")
        for registration in OpencodeProtocol.supported_hooks.values():
            assert f'hook_event_name: "{registration.native_name}"' in content

    def test_first_prompt_starts_the_session_and_context_is_added_without_a_new_turn(self, tmp_path: Path) -> None:
        cases = "*session.start*) printf start;; *session.prompt*) printf prompt;;"
        out, payloads = _run(tmp_path, cases, [_prompt(), _prompt(text="again")])

        assert out["synthetic"] == [
            {"sessionID": "main", "text": text, "resume": False} for text in ("start", "prompt", "prompt")
        ]
        assert [p["hook_event_name"] for p in payloads] == ["session.start", "session.prompt", "session.prompt"]
        assert payloads[1]["prompt"] == "hi"
        assert payloads[1]["cwd"] == payloads[1]["ran_in"] == str(tmp_path / "project")

    def test_session_that_has_run_before_starts_as_resume(self, tmp_path: Path) -> None:
        _, payloads = _run(tmp_path, "", [_prompt(session="resumed-1"), _prompt()])
        assert [p.get("source") for p in payloads if p["hook_event_name"] == "session.start"] == ["resume", "startup"]

    def test_hooks_run_in_the_sessions_own_directory(self, tmp_path: Path) -> None:
        _, payloads = _run(tmp_path, "", [_before(session="elsewhere")])
        assert payloads[0]["cwd"] == payloads[0]["ran_in"] == str(tmp_path / "other")

    def test_blocked_tool_call_throws(self, tmp_path: Path) -> None:
        cases = "*tool.execute.before*) printf nope >&2; exit 2;;"
        out, _ = _run(tmp_path, cases, [_before()])
        assert out["results"] == [{"error": "nope"}]

    def test_updated_input_replaces_the_input(self, tmp_path: Path) -> None:
        reply = json.dumps({"updated_input": {"command": "ls -a"}, "message": None})
        cases = f"*tool.execute.before*) printf '%s' '{reply}';;"
        out, _ = _run(tmp_path, cases, [_before()])
        assert out["results"][0]["input"] == {"command": "ls -a"}

    def test_notes_are_appended_to_the_tool_result(self, tmp_path: Path) -> None:
        cases = "*tool.execute.before*) printf before;; *tool.execute.after*) printf after;;"
        out, payloads = _run(tmp_path, cases, [_before(), _after()])
        assert out["results"][1]["result"]["content"] == [
            {"type": "text", "text": "done"},
            {"type": "text", "text": "before\n\nafter"},
        ]
        assert payloads[1]["tool_response"] == {"success": True, "result": "done"}

    def test_a_patch_is_checked_once_per_file(self, tmp_path: Path) -> None:
        patch = "*** Begin Patch\n*** Update File: a.py\n@@\n-x\n+y\n*** Add File: b.py\n+z\n*** End Patch"
        cases = "*b.py*) printf 'no b' >&2; exit 2;;"
        out, payloads = _run(tmp_path, cases, [_before(tool="patch", patchText=patch)])

        assert out["results"] == [{"error": "no b"}]
        assert [p["tool_input"]["patchText"] for p in payloads] == [
            "*** Begin Patch\n*** Update File: a.py\n@@\n-x\n+y\n*** End Patch",
            "*** Begin Patch\n*** Add File: b.py\n+z\n*** End Patch",
        ]

    def test_a_moved_file_is_also_checked_at_its_destination(self, tmp_path: Path) -> None:
        patch = "*** Begin Patch\n*** Update File: a.py\n*** Move to: b.py\n@@\n-x\n+y\n*** End Patch"
        _, payloads = _run(tmp_path, "", [_before(tool="patch", patchText=patch)])
        assert [p["tool_input"]["patchText"].splitlines()[1] for p in payloads] == [
            "*** Update File: a.py",
            "*** Update File: b.py",
        ]

    def test_mcp_tools_are_renamed(self, tmp_path: Path) -> None:
        _, payloads = _run(tmp_path, "", [_before(tool="my_memory_read_graph")])
        assert payloads[0]["tool_name"] == "mcp__my.memory__read_graph"

    def test_child_sessions_carry_the_agent_they_were_spawned_as(self, tmp_path: Path) -> None:
        steps = [
            _before(tool="subagent", agent="explore", prompt="look"),
            _prompt(session="child-1", text="look"),
            _before(session="child-1", call="c2", as_agent="explore"),
        ]
        _, payloads = _run(tmp_path, "", steps)
        assert all(p["agent_id"] == "child-1" and p["agent_type"] == "explore" for p in payloads[1:])
        assert payloads[0]["agent_type"] == ""

    def test_tool_events_update_the_child_sessions_agent(self, tmp_path: Path) -> None:
        steps = [
            _before(session="child-1", as_agent="explore"),
            _before(session="child-1", call="c2", as_agent="review"),
        ]
        _, payloads = _run(tmp_path, "", steps)
        assert [p["agent_type"] for p in payloads] == ["explore", "review"]

    def test_reused_child_session_carries_its_current_agent(self, tmp_path: Path) -> None:
        steps = [
            _before(tool="subagent", agent="explore", prompt="look"),
            _prompt(session="child-1", text="look"),
            _before(tool="subagent", call="c2", sessionID="child-1", agent="review", prompt="check"),
            _prompt(session="child-1", text="check"),
            _before(session="child-1", call="c3", as_agent="review"),
        ]
        _, payloads = _run(tmp_path, "", steps)
        assert [p["agent_type"] for p in payloads if p.get("agent_id") == "child-1"] == [
            "explore",
            "explore",
            "review",
            "review",
        ]

    def test_blocked_stop_continues_once_then_reports_the_stop_hook_active(self, tmp_path: Path) -> None:
        cases = "*session.idle*) printf 'keep going' >&2; exit 2;;"
        out, payloads = _run(tmp_path, cases, [_idle(), _idle(), _idle("child-1")])

        assert out["synthetic"] == [{"sessionID": "main", "text": "keep going"}] * 2
        assert [p["stop_hook_active"] for p in payloads] == [False, True]

    def test_stop_waits_for_the_sessions_own_background_work(self, tmp_path: Path) -> None:
        background = [{"kind": "subagent", "sessionID": "main", "childSessionID": "child-1"}]
        _, payloads = _run(tmp_path, "", [_idle(background=background)])
        assert payloads == []

    def test_compaction_context_is_added(self, tmp_path: Path) -> None:
        cases = "*session.compaction*) printf recap;;"
        step = {"hook": "session.compaction", "event": {"sessionID": "main", "system": []}}
        out, _ = _run(tmp_path, cases, [step])
        assert out["results"] == [{"sessionID": "main", "system": [{"type": "text", "text": "recap"}]}]
