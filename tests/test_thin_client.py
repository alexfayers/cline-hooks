from __future__ import annotations

import io
import json
import subprocess
import sys
from typing import TYPE_CHECKING
from urllib.error import URLError

import pytest

from cline_hooks.core.daemon_config import DaemonConfig
from cline_hooks.daemon import service
from cline_hooks.daemon.client import ENV_FIELD
import cline_hooks.thin_client as thin_client_module
from cline_hooks.thin_client import main

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
    mocker.patch.object(thin_client_module, "get_data_dir", return_value=tmp_path)
    mocker.patch.object(thin_client_module, "try_load", return_value=DaemonConfig(port=17654, token="tok"))
    mocker.patch.object(service, "is_installed", return_value=False)
    thin_client_module.logger.handlers.clear()


@pytest.fixture(autouse=True)
def spawn(mocker: MockerFixture) -> MagicMock:
    return mocker.patch.object(thin_client_module, "spawn")


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


def test_importing_the_thin_client_stays_light() -> None:
    script = (
        "import sys\n"
        "import cline_hooks.thin_client\n"
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
            {"exit_code": 0, "stdout": "some context", "stderr": ""},
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

    def test_allows_when_no_daemon_config_exists(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], urlopen: MagicMock
    ) -> None:
        mocker.patch.object(thin_client_module, "try_load", return_value=None)
        assert _run(mocker) == 0
        assert capsys.readouterr().out == ""
        urlopen.assert_not_called()

    @pytest.mark.parametrize(
        "body", [b"not json", json.dumps({"exit_code": 0}).encode("utf-8")], ids=["malformed", "missing-fields"]
    )
    def test_allows_on_an_unusable_answer(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], urlopen: MagicMock, body: bytes
    ) -> None:
        _reply(urlopen, body)
        assert _run(mocker) == 0
        assert capsys.readouterr().out == ""

    @pytest.mark.parametrize(
        ("error", "service_installed", "respawned"),
        [(_REFUSED, False, True), (_REFUSED, True, False), (TimeoutError("timed out"), False, False)],
        ids=["refused", "refused-with-managed-service", "timeout"],
    )
    def test_allows_on_a_failed_request_and_respawns_only_when_needed(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
        urlopen: MagicMock,
        spawn: MagicMock,
        error: Exception,
        service_installed: bool,
        respawned: bool,
    ) -> None:
        urlopen.side_effect = error
        mocker.patch.object(service, "is_installed", return_value=service_installed)
        assert _run(mocker) == 0
        assert capsys.readouterr().out == ""
        assert spawn.called is respawned

    def test_allows_when_respawn_fails(
        self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str], urlopen: MagicMock, spawn: MagicMock
    ) -> None:
        urlopen.side_effect = _REFUSED
        spawn.side_effect = OSError("no executable")
        assert _run(mocker) == 0
        assert capsys.readouterr().out == ""

    @pytest.mark.parametrize(
        ("stdin", "timeout"),
        [
            ('{"hook_event_name": "PreToolUse"}', thin_client_module._GUARD_TIMEOUT_SECONDS),
            ('{"hook_event_name": "PostToolUse"}', thin_client_module._POST_TOOL_USE_TIMEOUT_SECONDS),
            ('{"hook_event_name": "Stop"}', thin_client_module._DEFAULT_TIMEOUT_SECONDS),
            ("not json", thin_client_module._DEFAULT_TIMEOUT_SECONDS),
        ],
        ids=["pre-tool-use", "post-tool-use", "other-event", "unparseable"],
    )
    def test_picks_the_timeout_by_hook_event(
        self, mocker: MockerFixture, urlopen: MagicMock, stdin: str, timeout: int
    ) -> None:
        _run(mocker, stdin)
        assert urlopen.call_args.kwargs["timeout"] == timeout

    def test_forwards_the_process_environment_in_the_body(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, urlopen: MagicMock
    ) -> None:
        monkeypatch.setenv("CLINE_HOOKS_TEST_ENV", "forwarded")
        _run(mocker, '{"hook_event_name": "PreToolUse"}')
        sent = json.loads(_sent_body(urlopen))
        assert sent[ENV_FIELD]["CLINE_HOOKS_TEST_ENV"] == "forwarded"
        assert sent["hook_event_name"] == "PreToolUse"

    def test_sends_unparseable_stdin_unchanged(self, mocker: MockerFixture, urlopen: MagicMock) -> None:
        _run(mocker, "not json")
        assert _sent_body(urlopen) == "not json"
