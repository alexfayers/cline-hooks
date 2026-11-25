from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

import pytest

HARNESS = Path(__file__).parent / "pi_extension_harness.mjs"
TEMPLATE = Path(__file__).parents[1] / "src" / "cline_hooks" / "frontends" / "pi" / "extension.ts"

HOOK_TIMEOUT_MS = "35_000"
TEST_HOOK_TIMEOUT_MS = 500
HUNG_HOOK_SECONDS = 20

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def _run_harness(
    tmp_path: Path, cases: str, tool_input: dict[str, Any], *harness_args: str, read_stdin: str = "$(cat)"
) -> dict[str, Any]:
    binary = tmp_path / "cline-hook"
    binary.write_text(
        f'#!/bin/sh\ncase "{read_stdin}" in {cases}'
        ' *\'"source":"compact"\'*) printf recap;;'
        ' *\'"source":"startup"\'*) printf \'{"message":"ctx","system_message":"hello %s"}\' $CLINE_HOOKS_FRONTEND;;'
        " esac\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    script = tmp_path / "cline-hooks.ts"
    template = TEMPLATE.read_text(encoding="utf-8").replace("__CLINE_HOOK_BINARY__", str(binary))
    timeout_line = f"HOOK_TIMEOUT_MS = {HOOK_TIMEOUT_MS};"
    assert timeout_line in template
    script.write_text(template.replace(timeout_line, f"HOOK_TIMEOUT_MS = {TEST_HOOK_TIMEOUT_MS};"))
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps(tool_input), encoding="utf-8")
    completed = subprocess.run(
        ["node", str(HARNESS), str(script), str(input_file), *harness_args],  # ruff: ignore[start-process-with-partial-path]
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(completed.stdout)  # type: ignore[no-any-return]


def _run_extension(tmp_path: Path, hook_stdout: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    cases = f"*'\"hook_event_name\":\"tool_call\"'*) printf '%s' '{hook_stdout}';;"
    return _run_harness(tmp_path, cases, tool_input)


def _step(event: str, call_id: str, tool: str, parent: str | None = None, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"toolName": tool, "toolCallId": call_id, "input": {}}
    if parent:
        payload["parentToolCallId"] = parent
    if event == "tool_result":
        payload |= {"content": [{"type": "text", "text": "ok"}], "isError": False}
    return {"event": event, "payload": payload | overrides}


def _run_steps(
    tmp_path: Path, replies: dict[str, str], steps: list[dict[str, Any]], hold_until: Path | None = None
) -> dict[str, Any]:
    """Fires the steps in order. Each reply is keyed by hook event and tool name, e.g. `tool_result:inner`.

    With `hold_until`, every hook waits for that file to exist before it answers.
    """
    hold = f"while [ ! -e '{hold_until}' ]; do sleep 0.01; done; " if hold_until else ""
    cases = "".join(
        f'*\'"hook_event_name":"{event}","tool_name":"{tool}"\'*) {hold}printf \'%s\' \'{stdout}\';;'
        for (event, tool), stdout in ((key.split(":"), stdout) for key, stdout in replies.items())
    )
    steps_file = tmp_path / "steps.json"
    steps_file.write_text(json.dumps(steps), encoding="utf-8")
    return _run_harness(tmp_path, cases, {}, str(steps_file))


def test_the_updated_input_replaces_the_tool_input(tmp_path: Path) -> None:
    hook_stdout = json.dumps({"updated_input": {"task": "do it. hint"}, "message": "ctx"})
    result = _run_extension(tmp_path, hook_stdout, {"task": "do it", "definition": "worker"})
    assert result["input"] == {"task": "do it. hint"}
    assert result["content"][-1]["text"] == "ctx"


@pytest.mark.parametrize(
    ("env", "identity"),
    [
        ({"PI_CONTEXT_ROLE": "reader", "PI_CONTEXT_RUN_ID": "a1b2c3d4"}, '"agent_type":"reader","agent_id":"a1b2c3d4"'),
        (
            {
                "PI_CONTEXT_ROLE": "reader",
                "PI_CONTEXT_RUN_ID": "a1b2c3d4",
                "PI_HERDSMAN_AGENT_DEFINITION": "worker",
                "PI_HERDSMAN_RUN_ID": "run-9",
            },
            '"agent_type":"worker","agent_id":"run-9"',
        ),
    ],
    ids=["pi-context", "herdsman-wins"],
)
def test_the_child_identity_comes_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: dict[str, str], identity: str
) -> None:
    for name in ("PI_CONTEXT_ROLE", "PI_CONTEXT_RUN_ID", "PI_HERDSMAN_AGENT_DEFINITION", "PI_HERDSMAN_RUN_ID"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    cases = f"*'{identity}'*) printf '%s' '{{\"updated_input\":{{\"seen\":true}}}}';;"
    assert _run_harness(tmp_path, cases, {})["input"] == {"seen": True}


def test_plain_text_context_leaves_the_tool_input_alone(tmp_path: Path) -> None:
    result = _run_extension(tmp_path, "REMINDER: plain", {"task": "do it"})
    assert result["input"] == {"task": "do it"}
    assert result["content"][-1]["text"] == "REMINDER: plain"
    assert result["structuredContent"] == {"ok": True}


def test_a_pi_context_writer_sends_its_worktree_as_the_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PI_CONTEXT_WORKTREE", "/work/worktree")
    cases = '*\'"cwd":"/work/worktree"\'*\'"hook_event_name":"tool_call"\'*) printf in-worktree;;'
    assert _run_harness(tmp_path, cases, {"task": "do it"})["content"][-1]["text"] == "in-worktree"


def test_a_hook_still_running_at_the_timeout_is_killed_and_the_call_allowed(tmp_path: Path) -> None:
    pid_file = tmp_path / "hung.pid"
    cases = f'*\'"hook_event_name":"tool_call"\'*) sleep {HUNG_HOOK_SECONDS} & echo $! > {pid_file}; wait; exit 2;;'
    started = time.monotonic()
    result = _run_harness(tmp_path, cases, {"task": "do it"})
    assert result["blocked"] is False
    assert time.monotonic() - started < HUNG_HOOK_SECONDS
    hung_child = subprocess.run(
        ["ps", "-o", "stat=", "-p", pid_file.read_text().strip()],  # ruff: ignore[start-process-with-partial-path]
        capture_output=True,
        text=True,
        check=False,
    )
    assert hung_child.stdout.strip() in {"", "Z"}


def test_a_hook_that_exits_without_reading_its_payload_allows_the_call(tmp_path: Path) -> None:
    result = _run_harness(tmp_path, "", {"task": "x" * 1024 * 1024}, read_stdin="")
    assert result["blocked"] is False


def test_a_compaction_is_relayed_as_a_compact_task_start(tmp_path: Path) -> None:
    assert _run_extension(tmp_path, "", {"task": "do it"})["queued"][-1] == "recap"


def test_a_session_start_user_message_is_shown_and_its_context_queued(tmp_path: Path) -> None:
    result = _run_extension(tmp_path, "", {"task": "do it"})
    assert result["notified"] == ["hello pi"]
    assert "ctx" in result["queued"]


def test_a_reminder_from_a_nested_call_is_delivered_on_the_outer_result(tmp_path: Path) -> None:
    steps = [
        _step("tool_call", "c1", "script"),
        _step("tool_call", "c1/1", "inner", "c1"),
        _step("tool_result", "c1/1", "inner", "c1"),
        _step("tool_execution_end", "c1/1", "inner"),
        _step("tool_result", "c1", "script"),
    ]
    results = _run_steps(tmp_path, {"tool_result:inner": "REMINDER: build"}, steps)["results"]
    assert results[2] is None
    assert results[4]["content"][-1]["text"] == "REMINDER: build"


def test_identical_reminders_are_delivered_once_in_arrival_order(tmp_path: Path) -> None:
    steps = [_step("tool_call", "c1", "script")]
    for child in ("c1/1", "c1/2"):
        steps += [_step("tool_call", child, "inner", "c1"), _step("tool_result", child, "inner", "c1")]
    steps += [_step("tool_result", "c1", "script")]
    replies = {"tool_result:inner": "REMINDER: build", "tool_result:script": "REMINDER: script"}
    result = _run_steps(tmp_path, replies, steps)["results"][-1]
    assert result["content"][-1]["text"] == "REMINDER: build\n\nREMINDER: script"


def test_a_reminder_arriving_after_the_outer_result_is_queued_for_the_next_turn(tmp_path: Path) -> None:
    steps = [
        _step("tool_call", "c1", "script"),
        _step("tool_call", "c1/1", "inner", "c1"),
        _step("tool_result", "c1", "script"),
        _step("tool_execution_end", "c1", "script"),
        _step("tool_result", "c1/1", "inner", "c1"),
        _step("tool_result", "c1/1", "inner", "c1"),
    ]
    assert _run_steps(tmp_path, {"tool_result:inner": "REMINDER: late"}, steps)["queued"] == ["REMINDER: late"]


def test_a_reminder_after_the_outer_call_ended_without_a_result_is_queued(tmp_path: Path) -> None:
    steps = [
        _step("tool_call", "c1", "script"),
        _step("tool_call", "c1/1", "inner", "c1"),
        _step("tool_execution_end", "c1", "script"),
        _step("tool_result", "c1/1", "inner", "c1"),
    ]
    assert _run_steps(tmp_path, {"tool_result:inner": "REMINDER: late"}, steps)["queued"] == ["REMINDER: late"]


def test_a_reminder_arriving_after_the_session_changed_is_dropped(tmp_path: Path) -> None:
    steps = [
        _step("tool_call", "c1", "script"),
        _step("tool_call", "c1/1", "inner", "c1"),
        _step("tool_result", "c1", "script"),
        {"event": "session_start", "payload": {"reason": "new"}},
        _step("tool_result", "c1/1", "inner", "c1"),
    ]
    assert _run_steps(tmp_path, {"tool_result:inner": "REMINDER: late"}, steps)["queued"] == []


def test_reminders_from_deeper_calls_reach_only_their_own_outer_result(tmp_path: Path) -> None:
    steps = [
        _step("tool_call", "c1", "script"),
        _step("tool_call", "c2", "script"),
        _step("tool_call", "c1/1", "middle", "c1"),
        _step("tool_call", "c1/1/1", "deep", "c1/1"),
        _step("tool_result", "c1/1/1", "deep", "c1/1"),
        _step("tool_result", "c1/1", "middle", "c1"),
        _step("tool_result", "c2", "script"),
        _step("tool_result", "c1", "script"),
    ]
    replies = {"tool_result:deep": "REMINDER: deep", "tool_result:middle": "REMINDER: middle"}
    results = _run_steps(tmp_path, replies, steps)["results"]
    assert results[-1]["content"][-1]["text"] == "REMINDER: deep\n\nREMINDER: middle"
    assert results[-2] is None


def test_a_reminder_from_a_nested_hook_still_running_when_the_outer_call_ends_is_queued(tmp_path: Path) -> None:
    release = tmp_path / "release"
    steps = [
        _step("tool_execution_start", "c1", "script"),
        _step("tool_execution_start", "c1/1", "inner", "c1"),
        {**_step("tool_call", "c1/1", "inner", "c1"), "defer": True},
        _step("tool_result", "c1", "script"),
        _step("tool_execution_end", "c1", "script"),
        {"writeFile": str(release), "join": True},
    ]
    result = _run_steps(tmp_path, {"tool_call:inner": "REMINDER: pre"}, steps, hold_until=release)
    assert result["queued"] == ["REMINDER: pre"]


def test_a_reminder_from_a_nested_hook_still_running_when_the_session_changes_is_dropped(tmp_path: Path) -> None:
    release = tmp_path / "release"
    steps = [
        _step("tool_execution_start", "c1", "script"),
        _step("tool_execution_start", "c1/1", "inner", "c1"),
        {**_step("tool_call", "c1/1", "inner", "c1"), "defer": True},
        _step("tool_result", "c1", "script"),
        {"event": "session_start", "payload": {"reason": "new"}},
        {"writeFile": str(release), "join": True},
    ]
    result = _run_steps(tmp_path, {"tool_call:inner": "REMINDER: pre"}, steps, hold_until=release)
    assert result["queued"] == []
