from __future__ import annotations

import io
import json
import subprocess
import sys
from typing import TYPE_CHECKING
from urllib.error import URLError

import pytest

from cline_hooks.daemon import service
from cline_hooks.daemon.client import ENV_FIELD
from cline_hooks.daemon.config import DaemonConfig
import cline_hooks.guard as guard_module
from cline_hooks.guard import main

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock
    import urllib.request

    from pytest_mock import MockerFixture

_HEAVY_PREFIXES = (
    "cline_hooks.handlers",
    "cline_hooks.plugins",
    "cline_hooks.core.frontends",
    "cline_hooks.core.dispatch",
    "cline_hooks.frontends",
    "pydantic",
)
_ALLOW = json.dumps({"exit_code": 0, "stdout": "", "stderr": ""}).encode("utf-8")
_REFUSED = URLError(ConnectionRefusedError())


@pytest.fixture(autouse=True)
def _isolate(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.object(guard_module, "get_data_dir", return_value=tmp_path)
    mocker.patch.object(guard_module, "try_load", return_value=DaemonConfig(port=17654, token="tok"))
    mocker.patch.object(service, "is_installed", return_value=False)
    guard_module.logger.handlers.clear()


@pytest.fixture(autouse=True)
def spawn(mocker: MockerFixture) -> MagicMock:
    return mocker.patch.object(guard_module, "spawn")


@pytest.fixture
def urlopen(mocker: MockerFixture) -> MagicMock:
    urlopen = mocker.patch("urllib.request.urlopen")
    _reply(urlopen, _ALLOW)
    return urlopen


def _reply(urlopen: MagicMock, body: bytes) -> None:
    urlopen.return_value.__enter__.return_value.read.return_value = body


def _run(mocker: MockerFixture, stdin: str = "{}") -> int | str | None:
    mocker.patch.object(sys, "stdin", io.StringIO(stdin))
    with pytest.raises(SystemExit) as excinfo:
        main()
    return excinfo.value.code


def _sent_body(urlopen: MagicMock) -> str:
    request: urllib.request.Request = urlopen.call_args.args[0]
    assert isinstance(request.data, bytes)
    return request.data.decode("utf-8")


def test_importing_the_guard_stays_light() -> None:
    script = (
        "import sys\n"
        "import cline_hooks.guard\n"
        f"heavy = [name for name in sys.modules if name.startswith({_HEAVY_PREFIXES!r})]\n"
        "print(','.join(sorted(heavy)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    assert result.stdout.strip() == ""


class TestMain:
    @pytest.mark.parametrize(
        "answer",
        [
            {"exit_code": 2, "stdout": "", "stderr": "blocked: nope"},
            {"exit_code": 0, "stdout": "context", "stderr": ""},
        ],
        ids=["block", "allow-with-context"],
    )
    def test_replays_the_daemon_answer_verbatim(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        urlopen: MagicMock,
        answer: dict[str, int | str],
    ) -> None:
        _reply(urlopen, json.dumps(answer).encode("utf-8"))
        assert _run(mocker) == answer["exit_code"]
        captured = capsys.readouterr()
        assert (captured.out, captured.err) == (answer["stdout"], answer["stderr"])

    @pytest.mark.parametrize(
        ("reply", "error", "service_installed", "spawn_error", "respawned"),
        [
            (b"not json", None, False, None, False),
            (b'{"exit_code": 0}', None, False, None, False),
            (None, _REFUSED, False, None, True),
            (None, _REFUSED, True, None, False),
            (None, _REFUSED, False, OSError("no executable"), True),
            (None, TimeoutError("timed out"), False, None, False),
        ],
        ids=["malformed", "missing-fields", "refused", "refused-with-service", "respawn-fails", "timeout"],
    )
    def test_fails_open(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        urlopen: MagicMock,
        spawn: MagicMock,
        reply: bytes | None,
        error: Exception | None,
        service_installed: bool,
        spawn_error: OSError | None,
        respawned: bool,
    ) -> None:
        mocker.patch.object(service, "is_installed", return_value=service_installed)
        urlopen.side_effect = error
        spawn.side_effect = spawn_error
        if reply is not None:
            _reply(urlopen, reply)
        assert _run(mocker) == 0
        assert capsys.readouterr().out == ""
        assert spawn.called is respawned

    def test_fails_open_without_a_daemon_config(self, mocker: MockerFixture, urlopen: MagicMock) -> None:
        mocker.patch.object(guard_module, "try_load", return_value=None)
        assert _run(mocker) == 0
        urlopen.assert_not_called()

    @pytest.mark.parametrize(
        ("event", "timeout"),
        [("PreToolUse", 2), ("tool_call", 2), ("PostToolUse", 35), ("tool_result", 35), ("Stop", 5), ("not json", 5)],
    )
    def test_picks_the_timeout_by_hook_event(
        self, mocker: MockerFixture, urlopen: MagicMock, event: str, timeout: int
    ) -> None:
        _run(mocker, event if event == "not json" else json.dumps({"hook_event_name": event}))
        assert urlopen.call_args.kwargs["timeout"] == timeout

    @pytest.mark.parametrize("stdin", ['{"hook_event_name": "PreToolUse"}', "not json"], ids=["json", "unparseable"])
    def test_sends_json_with_the_process_environment_else_stdin_unchanged(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, urlopen: MagicMock, stdin: str
    ) -> None:
        monkeypatch.setenv("CLINE_HOOKS_TEST_ENV", "forwarded")
        _run(mocker, stdin)
        sent = _sent_body(urlopen)
        if stdin == "not json":
            assert sent == stdin
        else:
            assert json.loads(sent)[ENV_FIELD]["CLINE_HOOKS_TEST_ENV"] == "forwarded"
