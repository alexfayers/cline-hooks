from __future__ import annotations

import signal
import time
from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.daemon_config import DaemonConfig
from cline_hooks.daemon import fingerprint
import cline_hooks.daemon.lifecycle as lifecycle_module
from cline_hooks.daemon.lifecycle import ensure, read_pid, status, stop
from cline_hooks.daemon.server import package_version

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import Mock

    from pytest_mock import MockerFixture

_PID = 4321
_CONFIG = DaemonConfig(port=17654, token="t")


@pytest.fixture(autouse=True)
def isolate_pidfile(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.object(lifecycle_module, "_PIDFILE_PATH", tmp_path / "daemon.pid")


@pytest.fixture
def kill(mocker: MockerFixture) -> Mock:
    """Write a pidfile for `_PID` and stub out `os.kill`.

    Returns:
        The mocked `os.kill`.
    """
    lifecycle_module._write_pidfile(_PID)
    return mocker.patch("cline_hooks.daemon.lifecycle.os.kill")


@pytest.fixture
def healthz(mocker: MockerFixture) -> Mock:
    """Answer /healthz as the daemon at `_PID`.

    Returns:
        The mocked `probe_healthz`.
    """
    mocker.patch.object(lifecycle_module, "try_load", return_value=_CONFIG)
    mocker.patch.object(lifecycle_module, "load_or_create", return_value=_CONFIG)
    return mocker.patch.object(lifecycle_module, "probe_healthz", return_value={"pid": _PID})


class TestReadPid:
    def test_reads_a_written_pid(self) -> None:
        lifecycle_module._write_pidfile(_PID)
        assert read_pid() == _PID

    @pytest.mark.parametrize("content", [None, "not-a-pid"], ids=["missing", "corrupt"])
    def test_none_without_a_valid_pidfile(self, content: str | None) -> None:
        if content is not None:
            lifecycle_module._PIDFILE_PATH.write_text(content, encoding="utf-8")
        assert read_pid() is None


class TestStatus:
    def test_not_running_without_a_pidfile(self) -> None:
        assert status() == "Daemon is not running (no pidfile)."

    @pytest.mark.parametrize(
        ("kill_error", "expected"),
        [
            (None, f"Daemon is running (pid {_PID})."),
            (ProcessLookupError, f"Daemon is not running (stale pidfile, pid {_PID})."),
        ],
        ids=["alive", "stale"],
    )
    def test_reports_whether_the_pid_is_alive(
        self, kill: Mock, kill_error: type[Exception] | None, expected: str
    ) -> None:
        kill.side_effect = kill_error
        assert status() == expected


class TestStop:
    def test_no_pidfile_reports_nothing_to_stop(self) -> None:
        assert stop() == "No daemon pidfile found."

    @pytest.mark.parametrize("health", [None, {"pid": _PID + 1}], ids=["silent", "other-pid"])
    def test_does_not_signal_a_pid_the_daemon_does_not_answer_for(
        self, kill: Mock, healthz: Mock, health: dict[str, int] | None
    ) -> None:
        healthz.return_value = health
        assert stop() == f"No daemon answering for pid {_PID} (stale pidfile)."
        kill.assert_not_called()

    def test_reports_a_process_that_exits_before_the_signal(self, kill: Mock, healthz: Mock) -> None:
        kill.side_effect = ProcessLookupError
        assert stop() == f"No process running at pid {_PID} (stale pidfile)."

    @pytest.mark.parametrize("service_installed", [True, False])
    def test_warns_about_a_managed_service_only_when_one_is_installed(
        self, mocker: MockerFixture, kill: Mock, healthz: Mock, service_installed: bool
    ) -> None:
        mocker.patch.object(lifecycle_module.service, "is_installed", return_value=service_installed)
        result = stop()
        kill.assert_called_once_with(_PID, signal.SIGTERM)
        assert ("cline-hook daemon service stop" in result) is service_installed


class TestEnsure:
    @pytest.mark.parametrize(
        ("health", "service_installed", "spawned"),
        [({"pid": 1}, False, False), (None, False, True), (None, True, False)],
        ids=["answering", "silent", "silent-with-managed-service"],
    )
    def test_spawns_only_when_no_daemon_answers_and_no_service_manages_it(
        self,
        mocker: MockerFixture,
        healthz: Mock,
        health: dict[str, int] | None,
        service_installed: bool,
        spawned: bool,
    ) -> None:
        healthz.return_value = health
        mocker.patch.object(lifecycle_module.service, "is_installed", return_value=service_installed)
        spawn = mocker.patch.object(lifecycle_module, "spawn")
        ensure()
        assert spawn.called is spawned


class TestBindOrRecover:
    def test_returns_the_server_on_a_clean_bind(self, mocker: MockerFixture) -> None:
        sentinel = mocker.Mock()
        mocker.patch.object(lifecycle_module, "make_server", return_value=sentinel)

        result = lifecycle_module._bind_or_recover(DaemonConfig(port=17654, token="t"), 17654)

        assert result is sentinel

    def test_raises_on_a_collision_with_a_non_cline_hooks_process(self, mocker: MockerFixture) -> None:
        mocker.patch.object(lifecycle_module, "make_server", side_effect=OSError)
        mocker.patch.object(lifecycle_module, "probe_healthz", return_value=None)

        with pytest.raises(RuntimeError):
            lifecycle_module._bind_or_recover(DaemonConfig(port=17654, token="t"), 17654)

    def test_exits_quietly_for_a_same_version_daemon(self, mocker: MockerFixture) -> None:
        mocker.patch.object(lifecycle_module, "make_server", side_effect=OSError)
        same_version = {"version": package_version()}
        mocker.patch.object(lifecycle_module, "probe_healthz", return_value=same_version)

        result = lifecycle_module._bind_or_recover(DaemonConfig(port=17654, token="t"), 17654)

        assert result is None

    def test_retires_and_retries_for_a_different_version_daemon(self, mocker: MockerFixture) -> None:
        sentinel = mocker.Mock()
        make_server_mock = mocker.patch.object(lifecycle_module, "make_server", side_effect=[OSError, sentinel])
        mocker.patch.object(lifecycle_module, "probe_healthz", return_value={"version": "0.0.1"})
        post_retire = mocker.patch.object(lifecycle_module, "post_retire")
        mocker.patch.object(time, "sleep")

        result = lifecycle_module._bind_or_recover(DaemonConfig(port=17654, token="the-token"), 17654)

        post_retire.assert_called_once_with(17654, "the-token")
        assert make_server_mock.call_count == 2
        assert result is sentinel


class TestWatchdog:
    def test_retires_the_server_when_the_plugin_fingerprint_changes(self, mocker: MockerFixture) -> None:
        server = mocker.Mock()
        mocker.patch.object(time, "sleep")
        mocker.patch.object(fingerprint, "cached", side_effect=["startup", "startup", "changed"])

        lifecycle_module._watchdog(server, "startup")

        server.shutdown.assert_called_once_with()
