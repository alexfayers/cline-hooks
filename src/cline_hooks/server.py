"""The persistent hook server behind `cline-hook serve`, which runs each hook request in a forked child.

The module imports only the standard library, so `serve` can bind its socket before it imports the hook code.
"""

from __future__ import annotations

import contextlib
import fcntl
import io
import json
import logging
import os
from pathlib import Path
import resource
import select
import signal
import socket
import stat
import struct
import sys
import tempfile
import threading
import time
from typing import Any, NoReturn

logger = logging.getLogger("hooks.server")

V = 1
MIN_V = 1
ACK = b"A"
RETRY = b"R"

_DIR_MODE = 0o700
_SOCKET_UMASK = 0o177
_MAX_SOCKET_PATH_BYTES = 107
_LENGTH = struct.Struct(">I")
_PEER_CREDENTIALS = struct.Struct("3i")
_ENVELOPE_BYTES = 1024 * 1024
# Matches Claude Code's 60s default hook timeout and sits above the client deadlines.
_CHILD_DEADLINE_SECONDS = 60
_IDLE_EXIT_SECONDS = 30 * 60
_STALE_EXIT_CODE = 3
_BACKLOG = 64


def socket_dir() -> Path | None:
    """Return the private folder that holds the socket and lock, creating it, or None where none passes the check.

    The folder is `$XDG_RUNTIME_DIR/cline-hooks`, else `~/.cache/cline-hooks/run`. It must be a real folder,
    not a link, owned by this user with mode 0700, and short enough for the socket path to fit.

    Returns:
        The folder, or None.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    candidates = [Path(runtime) / "cline-hooks"] if runtime else []
    candidates.append(Path.home() / ".cache" / "cline-hooks" / "run")
    return next((path for path in candidates if _is_private_dir(path)), None)


def _is_private_dir(path: Path) -> bool:
    """Create `path` with mode 0700 where missing, and check it is a private folder that fits the socket path.

    Returns:
        Whether the socket can live in `path`.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(FileExistsError):
            path.mkdir(mode=_DIR_MODE)
        info = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISDIR(info.st_mode)
        and info.st_uid == os.getuid()
        and stat.S_IMODE(info.st_mode) == _DIR_MODE
        and len(os.fsencode(path / "hook.sock")) <= _MAX_SOCKET_PATH_BYTES
    )


def fingerprint_files() -> tuple[str, list[Path]]:
    """Return the cline-hooks version and the RECORD files of cline-hooks and of every plugin distribution.

    shortcut: a plugin distribution installed after the server starts is not detected until it restarts.

    Returns:
        The version and the RECORD paths.
    """
    from importlib.metadata import (  # ruff: ignore[import-outside-top-level]
        PathDistribution,
        distribution,
        entry_points,
    )

    own = distribution("cline-hooks")
    dists = [own, *(ep.dist for ep in entry_points(group="cline_hooks") if ep.dist is not None)]
    records = [
        Path(str(dist._path)) / "RECORD"  # ruff: ignore[private-member-access]
        for dist in dists
        if isinstance(dist, PathDistribution)
    ]
    return own.version, records


def fingerprint(version: str, records: list[Path]) -> str:
    """Return `version` plus the mtime of each RECORD file, which changes on each reinstall.

    Returns:
        The fingerprint.
    """
    mtimes = []
    for record in records:
        try:
            mtimes.append(str(record.stat().st_mtime_ns))
        except OSError:
            mtimes.append("-")
    return "|".join([version, *mtimes])


def _read_exact(conn: socket.socket, size: int) -> bytes | None:
    """Read exactly `size` bytes.

    Returns:
        The bytes, or None where the peer closed first.
    """
    chunks = bytearray()
    while len(chunks) < size:
        chunk = conn.recv(min(size - len(chunks), 1024 * 1024))
        if not chunk:
            return None
        chunks += chunk
    return bytes(chunks)


def _read_request(conn: socket.socket, max_bytes: int) -> dict[str, Any] | None:
    """Read one length-prefixed JSON request of at most `max_bytes`.

    Returns:
        The request, or None where it is too large, cut short or malformed.
    """
    header = _read_exact(conn, _LENGTH.size)
    if header is None:
        return None
    (size,) = _LENGTH.unpack(header)
    body = _read_exact(conn, size) if size <= max_bytes else None
    if body is None:
        return None
    try:
        request = json.loads(body)
    except ValueError:
        return None
    valid = (
        isinstance(request, dict)
        and isinstance(request.get("v"), int)
        and isinstance(request.get("cwd"), str)
        and isinstance(request.get("env"), dict)
        and all(isinstance(key, str) and isinstance(value, str) for key, value in request["env"].items())
        and isinstance(request.get("stdin"), str)
    )
    return request if valid else None


def _reply(conn: socket.socket, code: int, stdout: str, stderr: str) -> None:
    body = json.dumps({"code": code, "stdout": stdout, "stderr": stderr}).encode()
    conn.sendall(_LENGTH.pack(len(body)) + body)


def _exit_code(error: SystemExit) -> int:
    """Return the exit status Python gives a process that raised `error`, printing a message code to stderr.

    Returns:
        The exit status.
    """
    if error.code is None:
        return 0
    if isinstance(error.code, int):
        return error.code
    print(error.code, file=sys.stderr)  # ruff: ignore[print]
    return 1


def _run_request(request: dict[str, Any]) -> int:
    """Run one hook request in this process, as `cline-hook` with no arguments does.

    Returns:
        The hook's exit status.
    """
    from cline_hooks import _main  # ruff: ignore[import-outside-top-level]

    sys.stdin = io.StringIO(request["stdin"])
    logging.root.handlers.clear()
    _main._configure_logging()  # ruff: ignore[private-member-access]
    try:
        _main._limit_resources()  # ruff: ignore[private-member-access]
        _main._run_hook()  # ruff: ignore[private-member-access]
    except SystemExit as error:
        return _exit_code(error)
    return 0


def _answer(conn: socket.socket, server: _Server) -> int:
    """Read one request from `conn`, run it and send the reply.

    Returns:
        The child's exit status, which is `_STALE_EXIT_CODE` where the request needs newer code.
    """
    from cline_hooks._main import _MAX_PAYLOAD_CHARS  # ruff: ignore[import-outside-top-level]

    request = _read_request(conn, _MAX_PAYLOAD_CHARS + _ENVELOPE_BYTES)
    if request is None or request["v"] < MIN_V:
        conn.sendall(RETRY)
        return 0
    if request["v"] > V or fingerprint(*server.records) != server.fingerprint:
        conn.sendall(RETRY)
        return _STALE_EXIT_CODE
    conn.sendall(ACK)
    try:
        os.chdir(request["cwd"])
    except OSError:
        _reply(conn, 0, "", "")
        return 0
    os.environ.clear()
    os.environ.update(request["env"])
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        os.dup2(out.fileno(), 1)
        os.dup2(err.fileno(), 2)
        code = _run_request(request)
        sys.stdout.flush()
        sys.stderr.flush()
        outputs = []
        for file in (out, err):
            file.seek(0)
            outputs.append(file.read().decode(errors="replace"))
    _reply(conn, code, *outputs)
    return 0


def _child(conn: socket.socket, inherited: list[int], server: _Server) -> NoReturn:
    """Answer one connection in a forked child, in its own process group, then exit."""
    signal.set_wakeup_fd(-1)
    for signum in (signal.SIGCHLD, signal.SIGTERM):
        signal.signal(signum, signal.SIG_DFL)
    for fd in inherited:
        with contextlib.suppress(OSError):
            os.close(fd)
    with contextlib.suppress(OSError):
        os.setpgid(0, 0)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        status = _answer(conn, server)
    except BaseException:
        logger.exception("The hook server child failed")
        status = 1
    os._exit(status)


def _peer_uid(conn: socket.socket) -> int:
    """Return the uid of the process at the other end of `conn`.

    Returns:
        The uid.
    """
    _pid, uid, _gid = _PEER_CREDENTIALS.unpack(
        conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _PEER_CREDENTIALS.size)
    )
    return int(uid)


class _Server:
    """The single-threaded accept loop, which forks one child per connection and tracks it until reaped."""

    def __init__(self, listener: socket.socket, lock_fd: int, socket_path: Path) -> None:
        self.listener: socket.socket | None = listener
        self.lock_fd: int | None = lock_fd
        self.socket_path = socket_path
        self.children: dict[int, tuple[socket.socket, float]] = {}
        self.stopping = False
        self.idle_since = time.monotonic()
        self.wake_read, self.wake_write = os.pipe()
        for fd in (self.wake_read, self.wake_write):
            os.set_blocking(fd, False)
        self.records: tuple[str, list[Path]] = ("", [])
        self.fingerprint = ""
        signal.set_wakeup_fd(self.wake_write)
        signal.signal(signal.SIGCHLD, lambda *_: None)
        signal.signal(signal.SIGTERM, self._on_term)

    def shutdown(self) -> None:
        """Stop accepting and release the lock, so a new server can start while the children finish."""
        if self.listener is not None:
            self.listener.close()
            self.listener = None
            with contextlib.suppress(FileNotFoundError):
                self.socket_path.unlink()
        if self.lock_fd is not None:
            os.ftruncate(self.lock_fd, 0)
            os.close(self.lock_fd)
            self.lock_fd = None

    def run(self) -> None:
        """Serve until stopped, idle for 30 minutes or stale, then wait for the running children."""
        self.records = fingerprint_files()
        self.fingerprint = fingerprint(*self.records)
        while True:
            if self.stopping:
                self.shutdown()
            now = time.monotonic()
            if self.listener is not None and not self.children and now - self.idle_since >= _IDLE_EXIT_SECONDS:
                logger.info("Stopping the hook server after %d idle seconds", _IDLE_EXIT_SECONDS)
                self.shutdown()
            if self.listener is None and not self.children:
                return
            self._step(now)

    def _on_term(self, _signum: int, _frame: object) -> None:
        self.stopping = True

    def _step(self, now: float) -> None:
        """Wait for a connection, a hangup, a signal or the next deadline, then handle what happened."""
        poller = select.poll()
        poller.register(self.wake_read, select.POLLIN)
        if self.listener is not None:
            poller.register(self.listener, select.POLLIN)
        connections = {conn.fileno(): pid for pid, (conn, _deadline) in self.children.items()}
        for fd in connections:
            poller.register(fd, 0)
        deadlines = [deadline for _conn, deadline in self.children.values()]
        if self.listener is not None and not self.children:
            deadlines.append(self.idle_since + _IDLE_EXIT_SECONDS)
        timeout = max(0.0, min(deadlines) - now) if deadlines else None
        events = poller.poll(None if timeout is None else timeout * 1000)
        for fd, event in events:
            if fd == self.wake_read:
                with contextlib.suppress(BlockingIOError):
                    os.read(self.wake_read, 4096)
            elif self.listener is not None and fd == self.listener.fileno():
                self._accept()
            elif fd in connections and event & (select.POLLHUP | select.POLLERR):
                self._kill(connections[fd])
        now = time.monotonic()
        for pid, (_conn, deadline) in list(self.children.items()):
            if now >= deadline:
                self._kill(pid)
        self._reap()

    def _accept(self) -> None:
        if self.listener is None:
            return
        try:
            conn, _address = self.listener.accept()
        except (BlockingIOError, InterruptedError):
            return
        self.idle_since = time.monotonic()
        if _peer_uid(conn) != os.getuid():
            conn.close()
            return
        if threading.active_count() != 1:
            logger.warning("Stopping the hook server: it runs more than one thread")
            with contextlib.suppress(OSError):
                conn.sendall(RETRY)
            conn.close()
            self.shutdown()
            return
        inherited = [self.wake_read, self.wake_write, self.listener.fileno()]
        inherited += [child_conn.fileno() for child_conn, _deadline in self.children.values()]
        if self.lock_fd is not None:
            inherited.append(self.lock_fd)
        pid = os.fork()
        if pid == 0:
            _child(conn, inherited, self)
        with contextlib.suppress(OSError):
            os.setpgid(pid, pid)
        self.children[pid] = (conn, time.monotonic() + _CHILD_DEADLINE_SECONDS)

    def _kill(self, pid: int) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, signal.SIGKILL)

    def _reap(self) -> None:
        while self.children:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                pid = 0
            if pid == 0:
                return
            conn, _deadline = self.children.pop(pid, (None, 0.0))
            if conn is not None:
                conn.close()
            self.idle_since = time.monotonic()
            if os.waitstatus_to_exitcode(status) == _STALE_EXIT_CODE:
                logger.info("Stopping the hook server: a request needs newer code")
                self.shutdown()


def _acquire_lock(lock_path: Path) -> int | None:
    """Take the server lock without blocking.

    Returns:
        The lock file descriptor, or None where another server holds it.
    """
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def _listen(socket_path: Path) -> socket.socket:
    """Bind and listen on `socket_path` with mode 0600, replacing any stale socket.

    Returns:
        The listening socket.
    """
    with contextlib.suppress(FileNotFoundError):
        socket_path.unlink()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    previous = os.umask(_SOCKET_UMASK)
    try:
        listener.bind(str(socket_path))
    finally:
        os.umask(previous)
    listener.listen(_BACKLOG)
    listener.settimeout(0)
    return listener


def stop() -> int:
    """Send SIGTERM to the running server, if any.

    Returns:
        The exit status: 0, or 1 where no folder passes the check.
    """
    directory = socket_dir()
    if directory is None:
        return 1
    lock_path = directory / "hook.lock"
    if not lock_path.exists():
        return 0
    fd = _acquire_lock(lock_path)
    if fd is not None:
        os.close(fd)
        return 0
    with contextlib.suppress(ValueError, ProcessLookupError, PermissionError):
        os.kill(int(lock_path.read_text().strip()), signal.SIGTERM)
    return 0


def serve() -> int:
    """Run the hook server until it stops: take the lock, listen, import the hook code, then serve.

    Returns:
        The exit status: 0, or 1 off Linux or where no folder passes the check.
    """
    if not sys.platform.startswith("linux"):
        return 1
    directory = socket_dir()
    if directory is None:
        return 1
    lock_fd = _acquire_lock(directory / "hook.lock")
    if lock_fd is None:
        return 0
    os.ftruncate(lock_fd, 0)
    socket_path = directory / "hook.sock"
    try:
        listener = _listen(socket_path)
    except OSError:
        logger.exception("Could not listen on %s", socket_path)
        os.close(lock_fd)
        return 1
    os.write(lock_fd, f"{os.getpid()}\n".encode())
    server = _Server(listener, lock_fd, socket_path)
    try:
        import cline_hooks._main  # ruff: ignore[import-outside-top-level, unused-import]

        server.run()
    finally:
        server.shutdown()
    return 0
