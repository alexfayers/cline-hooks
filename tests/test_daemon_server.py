from __future__ import annotations

import http.client
import json
import os
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.daemon_config import DaemonConfig
from cline_hooks.core.outcome import Outcome
from cline_hooks.daemon.server import make_server, package_version

if TYPE_CHECKING:
    from collections.abc import Iterator
    from http.server import ThreadingHTTPServer

    from pytest_mock import MockerFixture

    from cline_hooks.core.models import HookInput

_TOKEN = "secret-token"

_POST_TOOL_USE_PAYLOAD = json.dumps({
    "hook_event_name": "PostToolUse",
    "session_id": "task-1",
    "cwd": "/workspace",
    "tool_name": "Read",
    "tool_input": {"file_path": "/tmp/example.py"},
})

_USER_PROMPT_PAYLOAD = json.dumps({
    "hook_event_name": "UserPromptSubmit",
    "session_id": "task-real-dispatch",
    "cwd": "/workspace",
    "prompt": "please help me understand this code",
})

_HANDLER_DELAY_SECONDS = 0.15
_STAGGER_SECONDS = 0.02


def _stop_payload(task_id: str) -> str:
    return json.dumps({"hook_event_name": "Stop", "session_id": task_id, "cwd": "/workspace"})


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


def _post(
    server: ThreadingHTTPServer, path: str, body: str, headers: dict[str, str] | None = None
) -> tuple[int, bytes]:
    port = server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("POST", path, body=body, headers=headers or {})
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


def _get(server: ThreadingHTTPServer, path: str, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    port = server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", path, headers=headers or {})
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


class TestHealthzEndpoint:
    def test_returns_identity_without_a_token(self, daemon_server: ThreadingHTTPServer) -> None:
        status, body = _get(daemon_server, "/healthz")
        assert status == 200
        parsed = json.loads(body)
        assert parsed["pid"] == os.getpid()
        assert parsed["version"] == package_version()
        assert isinstance(parsed["plugin_fingerprint"], str)
        assert isinstance(parsed["started_at"], float)

    def test_unknown_path_returns_404(self, daemon_server: ThreadingHTTPServer) -> None:
        status, _ = _get(daemon_server, "/not-healthz")
        assert status == 404

    def test_post_to_healthz_is_not_a_route(self, daemon_server: ThreadingHTTPServer) -> None:
        status, _ = _post(daemon_server, "/healthz", "", {"Authorization": f"Bearer {_TOKEN}"})
        assert status == 404


class TestRetireEndpoint:
    def test_valid_token_accepts_and_schedules_shutdown(
        self, daemon_server: ThreadingHTTPServer, mocker: MockerFixture
    ) -> None:
        shutdown = mocker.patch.object(daemon_server, "shutdown")

        status, body = _post(daemon_server, "/admin/retire", "", {"Authorization": f"Bearer {_TOKEN}"})

        assert status == 200
        assert json.loads(body) == {"status": "retiring"}
        for _ in range(20):
            if shutdown.called:
                break
            time.sleep(0.05)
        shutdown.assert_called_once()

    def test_wrong_bearer_token_returns_401(self, daemon_server: ThreadingHTTPServer) -> None:
        status, _ = _post(daemon_server, "/admin/retire", "", {"Authorization": "Bearer wrong-token"})
        assert status == 401


class TestRemovedHookEndpoint:
    def test_post_to_hook_returns_404(self, daemon_server: ThreadingHTTPServer) -> None:
        status, _ = _post(
            daemon_server,
            "/hook",
            _POST_TOOL_USE_PAYLOAD,
            {"Authorization": f"Bearer {_TOKEN}"},
        )
        assert status == 404


class TestHookCommandEndpoint:
    def test_valid_request_returns_the_real_handlers_command_shape(self, daemon_server: ThreadingHTTPServer) -> None:
        status, body = _post(
            daemon_server,
            "/hook/command",
            _USER_PROMPT_PAYLOAD,
            {"Authorization": f"Bearer {_TOKEN}"},
        )
        assert status == 200
        parsed = json.loads(body)
        assert parsed["exit_code"] == 0
        assert "TIME:" in json.loads(parsed["stdout"])["hookSpecificOutput"]["additionalContext"]
        assert parsed["stderr"] == ""

    def test_wrong_bearer_token_returns_401(self, daemon_server: ThreadingHTTPServer) -> None:
        status, _ = _post(
            daemon_server,
            "/hook/command",
            _POST_TOOL_USE_PAYLOAD,
            {"Authorization": "Bearer wrong-token"},
        )
        assert status == 401

    def test_missing_bearer_token_returns_401(self, daemon_server: ThreadingHTTPServer) -> None:
        status, _ = _post(daemon_server, "/hook/command", _POST_TOOL_USE_PAYLOAD)
        assert status == 401

    def test_malformed_body_still_fails_open_to_allow(self, daemon_server: ThreadingHTTPServer) -> None:
        status, body = _post(
            daemon_server,
            "/hook/command",
            "not json at all {{{",
            {"Authorization": f"Bearer {_TOKEN}"},
        )
        assert status == 200
        parsed = json.loads(body)
        assert parsed == {"exit_code": 0, "stdout": "", "stderr": ""}

    def test_same_task_id_requests_still_serialize(
        self, daemon_server: ThreadingHTTPServer, recorded_dispatch_events: list[tuple[str, str, float]]
    ) -> None:
        def send() -> None:
            _post(
                daemon_server,
                "/hook/command",
                _stop_payload("shared-command-task"),
                {"Authorization": f"Bearer {_TOKEN}"},
            )

        t1 = threading.Thread(target=send)
        t2 = threading.Thread(target=send)
        t1.start()
        time.sleep(_STAGGER_SECONDS)
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert len(recorded_dispatch_events) == 4
        first_end = next(t for kind, _, t in recorded_dispatch_events if kind == "end")
        second_start = sorted(t for kind, _, t in recorded_dispatch_events if kind == "start")[1]
        assert second_start >= first_end

    def test_different_task_ids_run_concurrently(
        self, daemon_server: ThreadingHTTPServer, recorded_dispatch_events: list[tuple[str, str, float]]
    ) -> None:
        def send(task_id: str) -> None:
            _post(
                daemon_server,
                "/hook/command",
                _stop_payload(task_id),
                {"Authorization": f"Bearer {_TOKEN}"},
            )

        t1 = threading.Thread(target=send, args=("task-a",))
        t2 = threading.Thread(target=send, args=("task-b",))
        t1.start()
        time.sleep(_STAGGER_SECONDS)
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert len(recorded_dispatch_events) == 4
        first_end = next(t for kind, _, t in recorded_dispatch_events if kind == "end")
        second_start = sorted(t for kind, _, t in recorded_dispatch_events if kind == "start")[1]
        assert second_start < first_end


class TestActiveProtocolIsolation:
    def test_concurrent_requests_each_see_their_own_active_protocol(
        self, daemon_server: ThreadingHTTPServer, mocker: MockerFixture
    ) -> None:
        """A ContextVar set on one request's thread must not leak into another's.

        This is the first time handlers run anywhere but a fresh subprocess,
        so per-thread isolation of `_active_protocol` is no longer free -
        prove it holds under real concurrent requests.
        """
        from cline_hooks.core.protocol import get_protocol
        from cline_hooks.frontends.claude_code import ClaudeCodeProtocol

        barrier = threading.Barrier(2, timeout=5)
        seen: dict[str, str] = {}
        seen_lock = threading.Lock()

        def fake_run_handler(protocol: object, hook: HookInput) -> Outcome:
            barrier.wait()
            active_protocol = get_protocol()
            assert isinstance(active_protocol, ClaudeCodeProtocol)
            rendered = active_protocol.render(Outcome.allow("marker"))
            with seen_lock:
                seen[hook.taskId] = json.loads(rendered.stdout)["hookSpecificOutput"]["hookEventName"]
            return Outcome.allow()

        mocker.patch("cline_hooks.daemon.server.run_handler", side_effect=fake_run_handler)

        def send(hook_event_name: str, task_id: str) -> None:
            payload = json.dumps({"hook_event_name": hook_event_name, "session_id": task_id, "cwd": "/workspace"})
            _post(daemon_server, "/hook/command", payload, {"Authorization": f"Bearer {_TOKEN}"})

        t1 = threading.Thread(target=send, args=("Stop", "task-stop"))
        t2 = threading.Thread(target=send, args=("SessionStart", "task-session-start"))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert seen == {"task-stop": "Stop", "task-session-start": "SessionStart"}


class TestHandlerRegistryPopulated:
    def test_importing_the_daemon_package_alone_populates_hook_handlers(self) -> None:
        """Regression guard for the known import trap.

        HOOK_HANDLERS is populated only as a side effect of `import
        cline_hooks.handlers`; the daemon must trigger that itself in a
        fresh process rather than relying on `_main.py` having done it
        first, or every request would silently return a default allow.
        """
        script = (
            "import cline_hooks.daemon.lifecycle\n"
            "from cline_hooks.core.registry import HOOK_HANDLERS\n"
            "import sys\n"
            "sys.exit(0 if HOOK_HANDLERS else 1)\n"
        )
        result = subprocess.run([sys.executable, "-c", script], check=False)
        assert result.returncode == 0


@pytest.fixture
def recorded_dispatch_events(mocker: MockerFixture) -> list[tuple[str, str, float]]:
    """Patch `run_handler` with a slow, event-recording stand-in for lock timing tests."""
    events: list[tuple[str, str, float]] = []
    events_lock = threading.Lock()

    def fake_run_handler(protocol: object, hook: HookInput) -> Outcome:
        with events_lock:
            events.append(("start", hook.taskId, time.monotonic()))
        time.sleep(_HANDLER_DELAY_SECONDS)
        with events_lock:
            events.append(("end", hook.taskId, time.monotonic()))
        return Outcome.allow()

    mocker.patch("cline_hooks.daemon.server.run_handler", side_effect=fake_run_handler)
    return events
