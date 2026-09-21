"""Loopback HTTP server answering the command-shaped relay endpoint every relayed hook calls through its thin client.

Binding to 127.0.0.1 is the access control - no separate peer/origin check.
`/hook/command` runs the real handler registered for the request's event and
renders its returned Outcome through the real `render()`.
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

from cline_hooks.core.dispatch import run_handler
from cline_hooks.core.outcome import Outcome
from cline_hooks.core.protocol import RawPayload, set_protocol
from cline_hooks.core.response import render
from cline_hooks.daemon import fingerprint, task_context
from cline_hooks.daemon.client import COMMAND_HOOK_PATH, HEALTHZ_PATH, RETIRE_PATH
from cline_hooks.frontends.claude_code import ClaudeCodeProtocol

if TYPE_CHECKING:
    from collections.abc import Iterator

    from cline_hooks.core.daemon_config import DaemonConfig

logger = logging.getLogger("hooks.daemon.server")

_started_at = 0.0

_task_locks: dict[str, threading.Lock] = {}
_task_lock_waiters: dict[str, int] = {}
_task_locks_registry_lock = threading.Lock()


@contextlib.contextmanager
def _task_lock(task_id: str) -> Iterator[None]:
    """Serialize requests sharing a `task_id`; a blank `task_id` never shares a lock.

    Evicts each per-task_id lock once nothing holds or is waiting on it, so a
    long-lived daemon does not accumulate one lock per session forever.
    """
    if not task_id:
        yield
        return

    with _task_locks_registry_lock:
        lock = _task_locks.setdefault(task_id, threading.Lock())
        _task_lock_waiters[task_id] = _task_lock_waiters.get(task_id, 0) + 1

    lock.acquire()
    try:
        yield
    finally:
        lock.release()
        with _task_locks_registry_lock:
            _task_lock_waiters[task_id] -= 1
            if _task_lock_waiters[task_id] <= 0:
                del _task_lock_waiters[task_id]
                del _task_locks[task_id]


def package_version() -> str:
    """Return the installed cline-hooks distribution version.

    Returns:
        The version string, or "0" if the package isn't installed as a
        distribution (e.g. running from a bare source checkout).
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

        Reads (and discards, where unneeded) the full request body up front,
        even on a rejected request - leaving it unread causes the kernel to
        RST the connection on close instead of a clean response.
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

        Parses via `ClaudeCodeProtocol` directly rather than `core.dispatch`'s
        generic frontend detection - this transport is exclusively Claude
        Code's, and a malformed/ambiguous body would otherwise misdetect as
        whichever frontend is `select_protocol`'s configured default.

        Returns:
            The handler's Outcome and the protocol it was parsed with.
        """
        payload = RawPayload(raw=body, data=_parse_body(body), env=os.environ)

        proto = ClaudeCodeProtocol.from_payload(payload)
        set_protocol(proto)
        hook = proto.parse(payload)
        task_context.task_id.set(hook.taskId)
        logger.info("hook=%s task=%s", hook.hookName, hook.taskId)

        with _task_lock(hook.taskId):
            outcome = run_handler(proto, hook)

        return outcome, proto

    def _handle_retire(self) -> None:
        """Answer 200 and shut the server down from a background thread.

        The shutdown runs off-thread so this handler can return and let the
        response flush - `HTTPServer.shutdown()` blocks until `serve_forever`
        notices, which would deadlock if called from the same request thread
        that must first finish sending this response.
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
