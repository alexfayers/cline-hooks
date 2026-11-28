from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import textwrap
import time
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="the hook server runs on Linux only")

FIXTURES_DIR = Path(__file__).parent / "fixtures"
_FIXTURES = sorted(path for frontend in ("claude-code", "pi") for path in FIXTURES_DIR.glob(f"*/{frontend}.json"))
_START_SECONDS = 10
_ACK = b"A"
_RETRY = b"R"
_SERVE = "import runpy, sys\nsys.argv = ['cline-hook', 'serve']\nrunpy.run_module('cline_hooks', run_name='__main__')\n"


class Server:
    """A `cline-hook serve` process with its own runtime directory and home."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.home = root / "home"
        self.runtime = root / "runtime"
        self.home.mkdir()
        self.runtime.mkdir(mode=0o700)
        self.process: subprocess.Popen[bytes] | None = None

    @property
    def env(self) -> dict[str, str]:
        return {
            "PATH": os.environ["PATH"],
            "HOME": str(self.home),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "LLM_PROMPTS_HOME": str(self.home / "llm-prompts"),
        }

    @property
    def socket_path(self) -> Path:
        return self.runtime / "cline-hooks" / "hook.sock"

    def run(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, "-m", "cline_hooks", "serve", *args],
            env=self.env,
            capture_output=True,
            timeout=_START_SECONDS,
            check=False,
        )

    def start(self, socket_path: Path | None = None, prelude: str | None = None) -> None:
        """Start the server, first running `prelude`, which patches it, where given."""
        command = ["-m", "cline_hooks", "serve"] if prelude is None else ["-c", textwrap.dedent(prelude) + _SERVE]
        self.process = subprocess.Popen([sys.executable, *command], env=self.env)
        wait_for((socket_path or self.socket_path).exists)

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
            self.process.wait()


def wait_for(condition: Callable[[], object]) -> None:
    deadline = time.monotonic() + _START_SECONDS
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail("timed out waiting for the hook server")
        time.sleep(0.01)


def _frame(body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + body


def _read_exact(conn: socket.socket, size: int) -> bytes:
    data = b""
    while len(data) < size:
        chunk = conn.recv(size - len(data))
        if not chunk:
            break
        data += chunk
    return data


def send(socket_path: Path, frame: bytes) -> tuple[bytes, dict[str, Any] | None]:
    """Send one raw frame and return the first reply byte and any reply that follows the ack.

    Returns:
        The first reply byte, and the decoded reply or None.
    """
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(_START_SECONDS * 3)
        conn.connect(str(socket_path))
        conn.sendall(frame)
        first = conn.recv(1)
        header = _read_exact(conn, 4) if first == _ACK else b""
        if len(header) < 4:
            return first, None
        (size,) = struct.unpack(">I", header)
        return first, json.loads(_read_exact(conn, size))


def request(
    socket_path: Path, stdin: str, env: dict[str, str], cwd: Path, v: int = 1
) -> tuple[bytes, dict[str, Any] | None]:
    body = json.dumps({"v": v, "cwd": str(cwd), "env": env, "stdin": stdin}).encode()
    return send(socket_path, _frame(body))


@pytest.fixture
def server(tmp_path: Path) -> Iterator[Server]:
    running = Server(tmp_path)
    yield running
    running.stop()


@pytest.mark.parametrize("fixture", _FIXTURES, ids=lambda path: f"{path.parent.name}/{path.stem}")
def test_a_request_answers_as_the_in_process_hook_does(server: Server, tmp_path: Path, fixture: Path) -> None:
    stdin = fixture.read_text(encoding="utf-8")
    in_process_env = {**server.env, "CLINE_HOOKS_DATA_DIR": str(tmp_path / "in-process")}
    served_env = {**server.env, "CLINE_HOOKS_DATA_DIR": str(tmp_path / "served")}
    expected = subprocess.run(
        [sys.executable, "-m", "cline_hooks"],
        input=stdin,
        env=in_process_env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    server.start()

    first, reply = request(server.socket_path, stdin, served_env, tmp_path)

    assert first == _ACK
    assert reply == {"code": expected.returncode, "stdout": expected.stdout, "stderr": expected.stderr}


def _allow_stdin() -> str:
    return (FIXTURES_DIR / "PreToolUse" / "claude-code.json").read_text(encoding="utf-8")


def test_a_frame_over_the_size_cap_gets_retry_and_the_server_stays_up(server: Server, tmp_path: Path) -> None:
    server.start()

    first, _reply = send(server.socket_path, struct.pack(">I", 2**31))

    assert first == _RETRY
    assert request(server.socket_path, _allow_stdin(), server.env, tmp_path)[0] == _ACK


def test_a_version_below_the_minimum_gets_retry_and_the_server_stays_up(server: Server, tmp_path: Path) -> None:
    server.start()

    first, _reply = request(server.socket_path, _allow_stdin(), server.env, tmp_path, v=0)

    assert first == _RETRY
    assert request(server.socket_path, _allow_stdin(), server.env, tmp_path)[0] == _ACK


def test_a_version_above_the_server_gets_retry_and_the_server_stops(server: Server, tmp_path: Path) -> None:
    server.start()

    first, _reply = request(server.socket_path, _allow_stdin(), server.env, tmp_path, v=2)

    assert first == _RETRY
    assert server.process is not None
    assert server.process.wait(timeout=_START_SECONDS) == 0
    assert not server.socket_path.exists()


def test_a_second_server_exits_while_one_runs(server: Server) -> None:
    server.start()

    assert server.run().returncode == 0
    assert server.process is not None
    assert server.process.poll() is None


def test_stop_ends_the_running_server(server: Server) -> None:
    server.start()
    wait_for((server.socket_path.parent / "hook.lock").read_text)

    assert server.run("--stop").returncode == 0
    assert server.process is not None
    assert server.process.wait(timeout=_START_SECONDS) == 0
    assert not server.socket_path.exists()


def test_stop_without_a_server_succeeds(server: Server) -> None:
    assert server.run("--stop").returncode == 0


def test_a_missing_cwd_is_allowed(server: Server, tmp_path: Path) -> None:
    server.start()

    reply = request(server.socket_path, _allow_stdin(), server.env, tmp_path / "missing")

    assert reply == (_ACK, {"code": 0, "stdout": "", "stderr": ""})


@pytest.mark.parametrize("problem", ["symlink", "mode", "long path"])
def test_a_runtime_folder_that_fails_the_check_falls_back_to_the_cache(server: Server, problem: str) -> None:
    if problem == "symlink":
        (server.root / "elsewhere").mkdir(mode=0o700)
        (server.runtime / "cline-hooks").symlink_to(server.root / "elsewhere")
    elif problem == "mode":
        (server.runtime / "cline-hooks").mkdir(mode=0o755)
        (server.runtime / "cline-hooks").chmod(0o755)
    else:
        server.runtime /= "x" * 100
        server.runtime.mkdir(mode=0o700)

    server.start(server.home / ".cache" / "cline-hooks" / "run" / "hook.sock")

    assert not server.socket_path.exists()


def test_each_request_runs_in_its_own_cwd_and_env(server: Server, tmp_path: Path) -> None:
    server.start()
    stdin = (FIXTURES_DIR / "UserPromptSubmit" / "claude-code.json").read_text(encoding="utf-8")
    replies = []
    for name in ("one", "two"):
        cwd = tmp_path / name
        cwd.mkdir()
        env = {**server.env, "CLINE_HOOKS_DATA_DIR": str(cwd / "data")}
        replies.append(request(server.socket_path, stdin, env, cwd))

    assert [reply[0] for reply in replies] == [_ACK, _ACK]
    assert (tmp_path / "one" / "data").is_dir()
    assert (tmp_path / "two" / "data").is_dir()


def _patch_hook(body: str) -> str:
    """Return a prelude that replaces the hook run with `body`."""
    return (
        "import os, sys, time\nimport cline_hooks._main\ndef _hook():\n"
        + textwrap.indent(textwrap.dedent(body), "    ")
        + "cline_hooks._main._run_hook = _hook\n"
    )


@pytest.mark.parametrize("crash", ["os._exit(1)", "os.abort()"])
def test_a_crashing_child_gives_eof_after_the_ack_at_once(server: Server, tmp_path: Path, crash: str) -> None:
    prelude = "import resource\nresource.setrlimit(resource.RLIMIT_CORE, (resource.RLIM_INFINITY,) * 2)\n"
    server.start(prelude=prelude + _patch_hook(crash + "\n"))
    started = time.monotonic()

    assert request(server.socket_path, _allow_stdin(), server.env, tmp_path) == (_ACK, None)
    assert time.monotonic() - started < _START_SECONDS


def test_a_large_stdout_comes_back_whole(server: Server, tmp_path: Path) -> None:
    server.start(prelude=_patch_hook("sys.stdout.write('x' * 200_000)\n"))

    first, reply = request(server.socket_path, _allow_stdin(), server.env, tmp_path)

    assert first == _ACK
    assert reply == {"code": 0, "stdout": "x" * 200_000, "stderr": ""}


def test_a_child_past_its_deadline_is_killed(server: Server, tmp_path: Path) -> None:
    prelude = "import cline_hooks.server\ncline_hooks.server._CHILD_DEADLINE_SECONDS = 0.5\n"
    server.start(prelude=prelude + _patch_hook("time.sleep(60)\n"))
    started = time.monotonic()

    assert request(server.socket_path, _allow_stdin(), server.env, tmp_path) == (_ACK, None)
    assert time.monotonic() - started < _START_SECONDS


def test_a_client_hangup_kills_the_child(server: Server, tmp_path: Path) -> None:
    pid_file = tmp_path / "child.pid"
    server.start(prelude=_patch_hook(f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\ntime.sleep(60)\n"))
    body = json.dumps({"v": 1, "cwd": str(tmp_path), "env": server.env, "stdin": _allow_stdin()}).encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.connect(str(server.socket_path))
        conn.sendall(_frame(body))
        assert conn.recv(1) == _ACK
        wait_for(lambda: pid_file.exists() and pid_file.read_text())
    pid = int(pid_file.read_text())

    def gone() -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        return False

    wait_for(gone)


def test_a_peer_with_another_uid_is_refused(server: Server) -> None:
    server.start(
        prelude="import os\nimport cline_hooks.server\ncline_hooks.server._peer_uid = lambda _conn: os.getuid() + 1\n"
    )

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(_START_SECONDS)
        conn.connect(str(server.socket_path))

        assert conn.recv(1) == b""


def test_a_folder_owned_by_another_user_is_refused(server: Server) -> None:
    prelude = "import os\n_uid = os.getuid() + 1\nos.getuid = lambda: _uid\n"
    result = subprocess.run(
        [sys.executable, "-c", prelude + _SERVE], env=server.env, timeout=_START_SECONDS, check=False
    )

    assert result.returncode == 1
    assert not server.socket_path.exists()
    assert not (server.home / ".cache" / "cline-hooks" / "run" / "hook.sock").exists()


def test_the_server_binds_before_it_imports_the_hook_code(server: Server, tmp_path: Path) -> None:
    marker = tmp_path / "loaded"
    server.start(
        prelude=f"""
        import sys
        import cline_hooks.server
        _listen = cline_hooks.server._listen
        def _record(path):
            open({str(marker)!r}, "w").write(str("cline_hooks._main" in sys.modules))
            return _listen(path)
        cline_hooks.server._listen = _record
        """
    )

    assert marker.read_text() == "False"


def test_stop_spares_a_stale_pid_while_a_new_server_starts(server: Server, tmp_path: Path) -> None:
    marker = tmp_path / "listening"
    bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    lock = server.runtime / "cline-hooks" / "hook.lock"
    lock.parent.mkdir(mode=0o700)
    lock.write_text(f"{bystander.pid}\n")
    try:
        server.process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time\nimport cline_hooks.server\n"
                f"cline_hooks.server._listen = lambda path: (open({str(marker)!r}, 'w').close(), time.sleep(60))\n"
                + _SERVE,
            ],
            env=server.env,
        )
        wait_for(marker.exists)

        assert server.run("--stop").returncode == 0
        time.sleep(0.2)
        assert bystander.poll() is None
    finally:
        bystander.send_signal(signal.SIGKILL)
        bystander.wait()
