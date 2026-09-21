from __future__ import annotations

import io
import json
import subprocess
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

from cline_hooks.core.daemon_config import DaemonConfig
import cline_hooks.thin_client as thin_client_module
from cline_hooks.thin_client import main

if TYPE_CHECKING:
    from pathlib import Path

_HEAVY_PREFIXES = (
    "cline_hooks.handlers",
    "cline_hooks.plugins",
    "cline_hooks.core.frontends",
    "cline_hooks.core.dispatch",
    "cline_hooks.frontends",
    "pydantic",
)


def _fake_response(body: bytes) -> MagicMock:
    response = MagicMock()
    response.read.return_value = body
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


@pytest.fixture(autouse=True)
def _isolate_logging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(thin_client_module, "get_data_dir", lambda: tmp_path)
    thin_client_module.logger.handlers.clear()


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
    def test_replays_a_block_decision_verbatim(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO('{"hook_event_name": "PreToolUse"}'))
        monkeypatch.setattr(thin_client_module, "try_load", lambda: DaemonConfig(port=17654, token="tok"))
        body = json.dumps({"exit_code": 2, "stdout": "", "stderr": "blocked: nope"}).encode("utf-8")
        with (
            patch("urllib.request.urlopen", return_value=_fake_response(body)),
            pytest.raises(SystemExit) as excinfo,
        ):
            main()
        assert excinfo.value.code == 2
        captured = capsys.readouterr()
        assert captured.err == "blocked: nope"
        assert captured.out == ""

    def test_replays_an_allow_with_context_verbatim(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        monkeypatch.setattr(thin_client_module, "try_load", lambda: DaemonConfig(port=17654, token="tok"))
        body = json.dumps({"exit_code": 0, "stdout": "some context", "stderr": ""}).encode("utf-8")
        with (
            patch("urllib.request.urlopen", return_value=_fake_response(body)),
            pytest.raises(SystemExit) as excinfo,
        ):
            main()
        assert excinfo.value.code == 0
        assert capsys.readouterr().out == "some context"

    def test_allows_when_no_daemon_config_exists(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        monkeypatch.setattr(thin_client_module, "try_load", lambda: None)
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0
        assert capsys.readouterr().out == ""

    def test_allows_on_connection_refused(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        monkeypatch.setattr(thin_client_module, "try_load", lambda: DaemonConfig(port=17654, token="tok"))
        with (
            patch("urllib.request.urlopen", side_effect=URLError("connection refused")),
            pytest.raises(SystemExit) as excinfo,
        ):
            main()
        assert excinfo.value.code == 0
        assert capsys.readouterr().out == ""

    def test_allows_on_timeout(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        monkeypatch.setattr(thin_client_module, "try_load", lambda: DaemonConfig(port=17654, token="tok"))
        with (
            patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")),
            pytest.raises(SystemExit) as excinfo,
        ):
            main()
        assert excinfo.value.code == 0
        assert capsys.readouterr().out == ""

    def test_allows_on_a_malformed_body(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        monkeypatch.setattr(thin_client_module, "try_load", lambda: DaemonConfig(port=17654, token="tok"))
        with (
            patch("urllib.request.urlopen", return_value=_fake_response(b"not json")),
            pytest.raises(SystemExit) as excinfo,
        ):
            main()
        assert excinfo.value.code == 0
        assert capsys.readouterr().out == ""

    def test_allows_on_a_body_missing_expected_fields(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        monkeypatch.setattr(thin_client_module, "try_load", lambda: DaemonConfig(port=17654, token="tok"))
        body = json.dumps({"exit_code": 0}).encode("utf-8")
        with (
            patch("urllib.request.urlopen", return_value=_fake_response(body)),
            pytest.raises(SystemExit) as excinfo,
        ):
            main()
        assert excinfo.value.code == 0
        assert capsys.readouterr().out == ""

    def test_uses_a_short_timeout_for_pretooluse(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO('{"hook_event_name": "PreToolUse"}'))
        monkeypatch.setattr(thin_client_module, "try_load", lambda: DaemonConfig(port=17654, token="tok"))
        body = json.dumps({"exit_code": 0, "stdout": "", "stderr": ""}).encode("utf-8")
        with (
            patch("urllib.request.urlopen", return_value=_fake_response(body)) as mock_urlopen,
            pytest.raises(SystemExit),
        ):
            main()
        assert mock_urlopen.call_args.kwargs["timeout"] == 2

    def test_uses_a_longer_timeout_for_other_hook_events(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO('{"hook_event_name": "Stop"}'))
        monkeypatch.setattr(thin_client_module, "try_load", lambda: DaemonConfig(port=17654, token="tok"))
        body = json.dumps({"exit_code": 0, "stdout": "", "stderr": ""}).encode("utf-8")
        with (
            patch("urllib.request.urlopen", return_value=_fake_response(body)) as mock_urlopen,
            pytest.raises(SystemExit),
        ):
            main()
        assert mock_urlopen.call_args.kwargs["timeout"] == 5

    def test_defaults_to_the_longer_timeout_on_unparseable_stdin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
        monkeypatch.setattr(thin_client_module, "try_load", lambda: DaemonConfig(port=17654, token="tok"))
        body = json.dumps({"exit_code": 0, "stdout": "", "stderr": ""}).encode("utf-8")
        with (
            patch("urllib.request.urlopen", return_value=_fake_response(body)) as mock_urlopen,
            pytest.raises(SystemExit),
        ):
            main()
        assert mock_urlopen.call_args.kwargs["timeout"] == 5

    def test_defaults_to_the_longer_timeout_when_hook_event_name_is_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
        monkeypatch.setattr(thin_client_module, "try_load", lambda: DaemonConfig(port=17654, token="tok"))
        body = json.dumps({"exit_code": 0, "stdout": "", "stderr": ""}).encode("utf-8")
        with (
            patch("urllib.request.urlopen", return_value=_fake_response(body)) as mock_urlopen,
            pytest.raises(SystemExit),
        ):
            main()
        assert mock_urlopen.call_args.kwargs["timeout"] == 5
