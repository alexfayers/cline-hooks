from __future__ import annotations

from datetime import UTC, datetime
import http.client
import json
import os
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING

import pytest

from cline_hooks.config import hook_env
from cline_hooks.core.daemon_config import DaemonConfig
from cline_hooks.core.dispatch import dispatch
from cline_hooks.core.outcome import Outcome
from cline_hooks.core.protocol import RawPayload, get_protocol
from cline_hooks.core.response import render
from cline_hooks.daemon.client import ENV_FIELD, probe_healthz
from cline_hooks.daemon.server import make_server, package_version
from cline_hooks.frontends.claude_code import ClaudeCodeProtocol
from cline_hooks.state.finished import mark_finished

if TYPE_CHECKING:
    from collections.abc import Iterator
    from http.server import ThreadingHTTPServer

    from pytest_mock import MockerFixture

    from cline_hooks.core.models import HookInput
    from cline_hooks.core.protocol import Protocol
    from cline_hooks.core.response import Response

_TOKEN = "secret-token"
_ENV_VAR = "CLINE_HOOKS_TEST_ENV"
_HANDLER_DELAY_SECONDS = 0.15
_STAGGER_SECONDS = 0.02

_USER_PROMPT_PAYLOAD = json.dumps({
    "hook_event_name": "UserPromptSubmit",
    "session_id": "task-real-dispatch",
    "cwd": "/workspace",
    "prompt": "please help me understand this code",
})


def _hook_payload(task_id: str, hook_event_name: str, **fields: object) -> str:
    return json.dumps({"hook_event_name": hook_event_name, "session_id": task_id, "cwd": "/workspace", **fields})


def _payload(
    task_id: str, hook_event_name: str = "Stop", env: dict[str, str] | str | None = None, agent_id: str = ""
) -> str:
    payload: dict[str, str | dict[str, str]] = {
        "hook_event_name": hook_event_name,
        "session_id": task_id,
        "cwd": "/workspace",
    }
    if agent_id:
        payload["agent_id"] = agent_id
    if env is not None:
        payload[ENV_FIELD] = env
    return json.dumps(payload)


@pytest.fixture
def daemon_server() -> Iterator[ThreadingHTTPServer]:
    server = make_server(DaemonConfig(port=0, token=_TOKEN), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def recorded_dispatch_events(mocker: MockerFixture) -> list[tuple[str, str, float]]:
    """Patch `run_handler` with a slow, event-recording stand-in for lock timing tests.

    Returns:
        The recorded (kind, task id, monotonic time) events.
    """
    events: list[tuple[str, str, float]] = []
    events_lock = threading.Lock()

    def fake_run_handler(protocol: Protocol, hook: HookInput) -> Outcome:
        with events_lock:
            events.append(("start", hook.taskId, time.monotonic()))
        time.sleep(_HANDLER_DELAY_SECONDS)
        with events_lock:
            events.append(("end", hook.taskId, time.monotonic()))
        return Outcome.allow()

    mocker.patch("cline_hooks.daemon.server.run_handler", side_effect=fake_run_handler)
    return events


def _request(
    server: ThreadingHTTPServer, method: str, path: str, body: str = "", token: str | None = _TOKEN
) -> tuple[int, bytes]:
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    try:
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


def _post_hook(server: ThreadingHTTPServer, body: str) -> tuple[int, bytes]:
    return _request(server, "POST", "/hook/command", body)


def _send_together(server: ThreadingHTTPServer, bodies: list[str], stagger: float = 0) -> None:
    threads = [threading.Thread(target=_post_hook, args=(server, body)) for body in bodies]
    for thread in threads:
        thread.start()
        time.sleep(stagger)
    for thread in threads:
        thread.join(timeout=5)


class TestHealthz:
    def test_returns_identity_without_a_token(self, daemon_server: ThreadingHTTPServer) -> None:
        status, body = _request(daemon_server, "GET", "/healthz", token=None)
        assert status == 200
        parsed = json.loads(body)
        assert parsed["pid"] == os.getpid()
        assert parsed["version"] == package_version()
        assert isinstance(parsed["plugin_fingerprint"], str)
        assert isinstance(parsed["started_at"], float)

    def test_probe_reads_a_live_daemon(self, daemon_server: ThreadingHTTPServer) -> None:
        health = probe_healthz(daemon_server.server_address[1])
        assert health is not None
        assert health["pid"] == os.getpid()

    def test_probe_returns_none_when_nothing_is_listening(self, daemon_server: ThreadingHTTPServer) -> None:
        port = daemon_server.server_address[1]
        daemon_server.shutdown()
        daemon_server.server_close()
        assert probe_healthz(port) is None


@pytest.mark.parametrize("path", ["/admin/retire", "/hook/command"])
@pytest.mark.parametrize("token", ["wrong-token", None], ids=["wrong", "missing"])
def test_rejects_a_wrong_or_missing_token(daemon_server: ThreadingHTTPServer, path: str, token: str | None) -> None:
    status, _ = _request(daemon_server, "POST", path, _payload("t"), token=token)
    assert status == 401


class TestRetire:
    def test_valid_token_accepts_and_schedules_shutdown(
        self, daemon_server: ThreadingHTTPServer, mocker: MockerFixture
    ) -> None:
        shutdown = mocker.patch.object(daemon_server, "shutdown")

        status, body = _request(daemon_server, "POST", "/admin/retire")

        assert status == 200
        assert json.loads(body) == {"status": "retiring"}
        for _ in range(20):
            if shutdown.called:
                break
            time.sleep(0.05)
        shutdown.assert_called_once()


class TestHookCommand:
    def test_valid_request_returns_the_real_handlers_command_shape(self, daemon_server: ThreadingHTTPServer) -> None:
        status, body = _post_hook(daemon_server, _USER_PROMPT_PAYLOAD)
        assert status == 200
        parsed = json.loads(body)
        assert parsed["exit_code"] == 0
        assert "TIME:" in json.loads(parsed["stdout"])["hookSpecificOutput"]["additionalContext"]
        assert parsed["stderr"] == ""

    def test_malformed_body_still_fails_open_to_allow(self, daemon_server: ThreadingHTTPServer) -> None:
        status, body = _post_hook(daemon_server, "not json at all {{{")
        assert status == 200
        assert json.loads(body) == {"exit_code": 0, "stdout": "", "stderr": ""}

    @pytest.mark.parametrize(
        ("bodies", "overlap"),
        [
            ([_payload("shared"), _payload("shared")], False),
            ([_payload("task-a"), _payload("task-b")], True),
            ([_payload("shared", agent_id="agent-1"), _payload("shared", agent_id="agent-2")], True),
            ([_payload("shared", "PostToolUse"), _payload("shared", "PreToolUse")], True),
        ],
        ids=["same-state-key", "different-tasks", "different-subagents", "pre-tool-use-skips-lock"],
    )
    def test_serializes_requests_per_state_key(
        self,
        daemon_server: ThreadingHTTPServer,
        recorded_dispatch_events: list[tuple[str, str, float]],
        bodies: list[str],
        overlap: bool,
    ) -> None:
        _send_together(daemon_server, bodies, stagger=_STAGGER_SECONDS)

        assert len(recorded_dispatch_events) == 4
        first_end = next(t for kind, _, t in recorded_dispatch_events if kind == "end")
        second_start = sorted(t for kind, _, t in recorded_dispatch_events if kind == "start")[1]
        assert (second_start < first_end) is overlap

    def test_concurrent_requests_each_see_their_own_protocol_and_env(
        self, daemon_server: ThreadingHTTPServer, mocker: MockerFixture
    ) -> None:
        barrier = threading.Barrier(2, timeout=5)
        seen: dict[str, tuple[str, str | None]] = {}
        seen_lock = threading.Lock()

        def fake_run_handler(protocol: Protocol, hook: HookInput) -> Outcome:
            barrier.wait()
            active_protocol = get_protocol()
            assert isinstance(active_protocol, ClaudeCodeProtocol)
            rendered = active_protocol.render(Outcome.allow("marker"))
            with seen_lock:
                seen[hook.taskId] = (
                    json.loads(rendered.stdout)["hookSpecificOutput"]["hookEventName"],
                    hook_env().get(_ENV_VAR),
                )
            return Outcome.allow()

        mocker.patch("cline_hooks.daemon.server.run_handler", side_effect=fake_run_handler)

        _send_together(
            daemon_server,
            [_payload("task-a", "Stop", {_ENV_VAR: "a"}), _payload("task-b", "SessionStart", {_ENV_VAR: "b"})],
        )

        assert seen == {"task-a": ("Stop", "a"), "task-b": ("SessionStart", "b")}

    @pytest.mark.parametrize(
        ("env", "expected"),
        [({_ENV_VAR: "forwarded"}, "forwarded"), (None, "daemon"), ("not a dict", "daemon")],
        ids=["forwarded", "absent", "malformed"],
    )
    def test_handlers_read_the_forwarded_env_else_the_daemons(
        self,
        daemon_server: ThreadingHTTPServer,
        mocker: MockerFixture,
        monkeypatch: pytest.MonkeyPatch,
        env: dict[str, str] | str | None,
        expected: str,
    ) -> None:
        monkeypatch.setenv(_ENV_VAR, "daemon")
        seen: dict[str, str | None] = {}

        def fake_run_handler(protocol: Protocol, hook: HookInput) -> Outcome:
            seen[hook.taskId] = hook_env().get(_ENV_VAR)
            return Outcome.allow()

        mocker.patch("cline_hooks.daemon.server.run_handler", side_effect=fake_run_handler)

        status, _ = _post_hook(daemon_server, _payload("t", env=env))

        assert status == 200
        assert seen == {"t": expected}


_PARITY_HOOKS = {
    "user-prompt": ("UserPromptSubmit", {"prompt": "please help me understand this code"}),
    "pre-tool-use": ("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "ls"}}),
    "post-tool-use": (
        "PostToolUse",
        {"tool_name": "Bash", "tool_input": {"command": "ls"}, "tool_response": {"stdout": "a"}},
    ),
    "post-tool-use-notebook-edit": (
        "PostToolUse",
        {
            "tool_name": "NotebookEdit",
            "tool_input": {"notebook_path": "/workspace/analysis.ipynb", "new_source": "print(1)"},
            "tool_response": {},
        },
    ),
    "stop": ("Stop", {}),
}


def _as_command_json(response: Response) -> dict[str, object]:
    return {"exit_code": response.exit_code, "stdout": response.stdout, "stderr": response.stderr}


@pytest.mark.parametrize(("hook_event_name", "fields"), _PARITY_HOOKS.values(), ids=_PARITY_HOOKS.keys())
def test_daemon_response_matches_in_process_render(
    daemon_server: ThreadingHTTPServer,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
    hook_event_name: str,
    fields: dict[str, object],
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    frozen = datetime(2026, 1, 1, 12, 30, tzinfo=UTC)
    mocker.patch("cline_hooks.handlers.user_prompt.local_now", return_value=frozen)
    mocker.patch("cline_hooks.plugins.nudges.local_now", return_value=frozen)
    mocker.patch("cline_hooks.plugins.nudges.random.random", return_value=1.0)

    in_process_body = _hook_payload("task-in-process", hook_event_name, **fields)
    in_process = render(dispatch(RawPayload.from_stdin(in_process_body)), get_protocol())
    _, daemon_body = _post_hook(daemon_server, _hook_payload("task-daemon", hook_event_name, **fields))

    assert json.loads(daemon_body) == _as_command_json(in_process)


def test_subagent_research_labelled_and_drained_via_daemon(
    daemon_server: ThreadingHTTPServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    lookup = {"tool_name": "WebFetch", "tool_input": {"url": "https://example.com/subagent-docs"}, "tool_response": {}}
    _post_hook(
        daemon_server,
        _hook_payload("task-research", "PostToolUse", agent_id="agent-7", agent_type="Explore", **lookup),
    )
    mark_finished("task-research:agent-7")

    _, body = _post_hook(daemon_server, _hook_payload("task-research", "Stop"))

    context = json.loads(json.loads(body)["stdout"])["hookSpecificOutput"]["additionalContext"]
    assert 'via Explore/agent-7: "https://example.com/subagent-docs"' in context


def test_importing_the_daemon_alone_populates_hook_handlers() -> None:
    script = (
        "import cline_hooks.daemon.lifecycle\n"
        "from cline_hooks.core.registry import HOOK_HANDLERS\n"
        "import sys\n"
        "sys.exit(0 if HOOK_HANDLERS else 1)\n"
    )
    assert subprocess.run([sys.executable, "-c", script], check=False).returncode == 0
