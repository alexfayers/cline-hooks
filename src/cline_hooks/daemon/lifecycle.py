"""Daemon process lifecycle: run in the foreground, spawn detached, stop, check status, or ensure."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING

from cline_hooks.config import config_dir
from cline_hooks.core.daemon_config import DaemonConfig, load_or_create
from cline_hooks.daemon import fingerprint, service, task_context
from cline_hooks.daemon.client import post_retire, probe_healthz
from cline_hooks.daemon.server import make_server, package_version
import cline_hooks.handlers  # ruff: ignore[unused-import]
from cline_hooks.state.paths import get_data_dir

if TYPE_CHECKING:
    from http.server import ThreadingHTTPServer

__all__ = ["ensure", "serve", "service", "spawn", "status", "stop"]

logger = logging.getLogger("hooks.daemon.lifecycle")

_PIDFILE_PATH = config_dir() / "daemon.pid"

_WATCHDOG_POLL_SECONDS = 5.0
_RETIRE_GRACE_SECONDS = 1.0


def _write_pidfile(pid: int) -> None:
    _PIDFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PIDFILE_PATH.write_text(str(pid), encoding="utf-8")


def read_pid() -> int | None:
    """Return the daemon's PID from the pidfile.

    Returns:
        The PID, or None if the pidfile is absent or unreadable.
    """
    try:
        return int(_PIDFILE_PATH.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def _configure_logging() -> None:
    """Route the "hooks" logger tree to a dedicated, task_id-stamped daemon log file.

    Not the shared cline-hooks.log: several processes appending to one
    FileHandler interleave, and the surviving PreToolUse `command` subprocess
    still writes to that shared file.
    """
    log_path = get_data_dir() / "cline-hooks-daemon.log"
    handler = logging.FileHandler(log_path)
    handler.addFilter(task_context.TaskIdFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s[%(task_id)s]: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    hooks_logger = logging.getLogger("hooks")
    hooks_logger.handlers.clear()
    hooks_logger.addHandler(handler)
    hooks_logger.propagate = False
    hooks_logger.setLevel(logging.DEBUG)


def _bind_or_recover(daemon_config: DaemonConfig, port: int) -> ThreadingHTTPServer | None:
    """Bind the server, recovering from a same-version daemon already owning the port.

    On a bind failure, probes /healthz on the target port: a same-version
    cline-hooks daemon means this process should exit quietly; a
    different-version one gets retired and the bind retried once; anything
    else is a genuine collision.

    Returns:
        The bound server, or None if a same-version daemon already owns
        the port and this process should exit quietly.

    Raises:
        RuntimeError: The port is held by something that isn't a
            cline-hooks daemon at all.
    """
    try:
        return make_server(daemon_config, port)
    except OSError:
        pass

    health = probe_healthz(port)
    if health is None:
        msg = f"Port {port} is already in use by something other than a cline-hooks daemon."
        logger.error(msg)
        raise RuntimeError(msg)

    if health.get("version") == package_version():
        logger.info("A cline-hooks daemon of the same version already owns port %d; exiting quietly.", port)
        return None

    logger.info(
        "Retiring a stale cline-hooks daemon (version %s) on port %d before starting.",
        health.get("version"),
        port,
    )
    post_retire(port, daemon_config.token)
    time.sleep(_RETIRE_GRACE_SECONDS)
    return make_server(daemon_config, port)


def _watchdog(server: ThreadingHTTPServer) -> None:
    """Poll for a stale plugin fingerprint, then retire so a supervisor can restart on the new code."""
    startup_fingerprint = fingerprint.cached()
    while True:
        time.sleep(_WATCHDOG_POLL_SECONDS)
        if fingerprint.cached() != startup_fingerprint:
            logger.info("Plugin fingerprint changed since startup; retiring")
            server.shutdown()
            return


def serve(port: int | None = None) -> None:
    """Run the daemon's HTTP server in the foreground (blocking).

    Args:
        port: Port to bind, or None to resolve it from the daemon config.
    """
    _configure_logging()
    daemon_config = load_or_create()
    bind_port = port if port is not None else daemon_config.port
    server = _bind_or_recover(daemon_config, bind_port)
    if server is None:
        return

    _write_pidfile(os.getpid())
    logger.info("Daemon listening on 127.0.0.1:%d (pid %d)", bind_port, os.getpid())
    threading.Thread(target=_watchdog, args=(server,), daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()


def spawn() -> None:
    """Start the daemon detached from the current process, redirecting its stdio to a log file."""
    log_path = get_data_dir() / "daemon.log"
    with log_path.open("a", encoding="utf-8") as log_file:
        subprocess.Popen(
            [sys.executable, "-m", "cline_hooks", "daemon", "serve"],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )


def ensure() -> None:
    """Start the daemon if it isn't already running and healthy.

    Connects and checks /healthz first, spawning a detached daemon only if
    nothing answers - the caller never waits on a cold daemon start.
    """
    daemon_config = load_or_create()
    if probe_healthz(daemon_config.port) is not None:
        return
    spawn()


def stop() -> str:
    """Stop the running daemon via its pidfile, if one is running.

    A managed service unit's restart policy is not scoped to this SIGTERM,
    so it will bring the daemon straight back up - warn rather than let that
    happen silently, and name the command that actually keeps it down.

    Returns:
        A human-readable status line.
    """
    pid = read_pid()
    if pid is None:
        return "No daemon pidfile found."
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return f"No process running at pid {pid} (stale pidfile)."

    result = f"Sent SIGTERM to daemon (pid {pid})."
    if service.is_installed():
        result += (
            " A managed service is installed and will restart it -"
            " use `cline-hook daemon service stop` to keep it stopped."
        )
    return result


def status() -> str:
    """Check whether the daemon appears to be running.

    Returns:
        A human-readable status line.
    """
    pid = read_pid()
    if pid is None:
        return "Daemon is not running (no pidfile)."
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return f"Daemon is not running (stale pidfile, pid {pid})."
    except PermissionError:
        return f"Daemon appears to be running (pid {pid})."
    return f"Daemon is running (pid {pid})."
