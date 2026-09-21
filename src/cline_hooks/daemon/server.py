"""Loopback HTTP server that answers hooks relayed by the thin client.

Binding to 127.0.0.1 is the access control; requests are also token-checked.
"""

from __future__ import annotations

import contextlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.metadata
import json
import logging
import os
import secrets
import threading
import time
from typing import TYPE_CHECKING, Any, ClassVar

from cline_hooks.config import set_hook_env
from cline_hooks.core.dispatch import run_handler
from cline_hooks.core.outcome import Outcome
from cline_hooks.core.protocol import RawPayload, set_protocol
from cline_hooks.core.response import render
from cline_hooks.core.vocabulary import CanonicalHook
from cline_hooks.daemon import fingerprint, task_context
from cline_hooks.daemon.client import COMMAND_HOOK_PATH, ENV_FIELD, HEALTHZ_PATH, RETIRE_PATH
from cline_hooks.frontends.claude_code import ClaudeCodeProtocol

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from cline_hooks.core.daemon_config import DaemonConfig

logger = logging.getLogger("hooks.daemon.server")

_started_at = 0.0

_task_locks: dict[str, threading.Lock] = {}
_task_lock_waiters: dict[str, int] = {}
_task_locks_registry_lock = threading.Lock()


@contextlib.contextmanager
def _task_lock(state_key: str) -> Iterator[None]:
    """Serialize requests sharing a state key; a blank key never shares a lock.

    Each lock is evicted once nothing holds or waits on it.
    """
    if not state_key:
        yield
        return

    with _task_locks_registry_lock:
        lock = _task_locks.setdefault(state_key, threading.Lock())
        _task_lock_waiters[state_key] = _task_lock_waiters.get(state_key, 0) + 1

    lock.acquire()
    try:
        yield
    finally:
        lock.release()
        with _task_locks_registry_lock:
            _task_lock_waiters[state_key] -= 1
            if _task_lock_waiters[state_key] <= 0:
                del _task_lock_waiters[state_key]
                del _task_locks[state_key]


def package_version() -> str:
    """Return the installed cline-hooks distribution version.

    Returns:
        The version string, or "0" if the package isn't installed as a
        distribution.
    """
    try:
        return importlib.metadata.version("cline-hooks")
    except importlib.metadata.PackageNotFoundError:
        return "0"


class HookRequestHandler(BaseHTTPRequestHandler):
    """Answers `/hook/command`, `/healthz`, and `/admin/retire`."""

    daemon_config: ClassVar[DaemonConfig]

    def do_GET(self) -> None:
        """Answer `GET /healthz` with this process's identity; anything else 404s."""
        if self.path != HEALTHZ_PATH:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return
        self._send_json(
            HTTPStatus.OK,
            {
                "pid": os.getpid(),
                "version": package_version(),
                "plugin_fingerprint": fingerprint.cached(),
                "started_at": _started_at,
            },
        )

    def do_POST(self) -> None:
        """Handle one `/hook/command` or `/admin/retire` POST request.

        The body is always read first; leaving it unread makes the kernel RST the connection.
        """
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else ""
        except Exception:
            logger.exception("Failed to read request body")
            self.send_response(HTTPStatus.BAD_REQUEST)
            self.end_headers()
            return

        if self.path not in {COMMAND_HOOK_PATH, RETIRE_PATH}:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return

        token = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not secrets.compare_digest(token, self.daemon_config.token):
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.end_headers()
            return

        if self.path == RETIRE_PATH:
            self._handle_retire()
            return

        try:
            outcome, proto = self._run_dispatch(body)
        except Exception:
            logger.exception("Unhandled error answering hook request")
            outcome, proto = Outcome.allow(), ClaudeCodeProtocol()
        self._respond_command(outcome, proto)

    def _run_dispatch(self, body: str) -> tuple[Outcome, ClaudeCodeProtocol]:
        """Parse the request body as a Claude Code hook payload and run the real handler.

        Returns:
            The handler's Outcome and the protocol it was parsed with.
        """
        data = _parse_body(body)
        env = _pop_env(data)
        set_hook_env(env)
        payload = RawPayload(raw=body if data is None else json.dumps(data), data=data, env=env)

        proto = ClaudeCodeProtocol.from_payload(payload)
        set_protocol(proto)
        hook = proto.parse(payload)
        task_context.task_id.set(hook.taskId)
        logger.info("hook=%s task=%s", hook.hookName, hook.taskId)

        with _task_lock("" if hook.hookName == CanonicalHook.PRE_TOOL_USE else hook.stateKey):
            outcome = run_handler(proto, hook)

        return outcome, proto

    def _handle_retire(self) -> None:
        """Answer 200 and shut the server down from a background thread.

        `shutdown()` runs off-thread: called from the request thread it would
        deadlock waiting on `serve_forever`.
        """
        logger.info("Retiring on request")
        self._send_json(HTTPStatus.OK, {"status": "retiring"})
        threading.Thread(target=self.server.shutdown, daemon=True).start()

    def _respond_command(self, outcome: Outcome, proto: ClaudeCodeProtocol) -> None:
        """Render `outcome` through the real `render()` and answer with the command shape."""
        response = render(outcome, proto)
        self._send_json(
            HTTPStatus.OK,
            {"exit_code": response.exit_code, "stdout": response.stdout, "stderr": response.stderr},
        )

    def _send_json(self, status: HTTPStatus, body: dict[str, Any] | None) -> None:
        """Send a JSON response by serializing `body` as JSON."""
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, log_format: str, *args: object) -> None:
        """Route the stdlib handler's own request log through this module's logger."""
        logger.debug(log_format, *args)


def _parse_body(body: str) -> dict[str, Any] | None:
    """Parse a request body as a JSON object.

    Returns:
        The parsed dict, or None if the body isn't valid JSON or isn't an object.
    """
    try:
        parsed = json.loads(body) if body else None
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _pop_env(data: dict[str, Any] | None) -> Mapping[str, str]:
    """Remove the forwarded hook-process environment from a parsed request body.

    Returns:
        The forwarded environment, or this process's own where the field is absent or malformed.
    """
    if data is None or ENV_FIELD not in data:
        return os.environ
    env = data.pop(ENV_FIELD)
    if not isinstance(env, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in env.items()
    ):
        logger.warning("Ignoring a malformed %s field", ENV_FIELD)
        return os.environ
    return env


def make_server(daemon_config: DaemonConfig, port: int) -> ThreadingHTTPServer:
    """Build the loopback HTTP server, bound but not yet serving.

    Args:
        daemon_config: The daemon's port/token config, used for token checks.
        port: The port to bind - pass 0 to let the OS assign one.

    Returns:
        The configured, unstarted server.
    """
    global _started_at  # ruff: ignore[global-statement]
    _started_at = time.time()
    handler_cls = type("_BoundHookRequestHandler", (HookRequestHandler,), {"daemon_config": daemon_config})
    return ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
