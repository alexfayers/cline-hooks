from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.daemon_config import DaemonConfig
import cline_hooks.daemon.lifecycle as lifecycle_module
from cline_hooks.daemon.lifecycle import ensure, read_pid, status, stop
from cline_hooks.daemon.server import package_version

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def isolate_pidfile(mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch.object(lifecycle_module, "_PIDFILE_PATH", tmp_path / "daemon.pid")


def _exited_pid() -> int:
    """Return a PID that has already exited, so it is guaranteed not running."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


class TestReadPid:
    def test_none_when_missing(self) -> None:
        assert read_pid() is None

    def test_reads_written_pid(self) -> None:
        lifecycle_module._write_pidfile(1234)
        assert read_pid() == 1234

    def test_none_on_corrupt_contents(self) -> None:
        lifecycle_module._PIDFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        lifecycle_module._PIDFILE_PATH.write_text("not-a-pid", encoding="utf-8")
        assert read_pid() is None


class TestStatus:
    def test_not_running_without_pidfile(self) -> None:
        assert status() == "Daemon is not running (no pidfile)."

    def test_running_for_the_current_process(self) -> None:
        lifecycle_module._write_pidfile(os.getpid())
        assert status() == f"Daemon is running (pid {os.getpid()})."

    def test_stale_pidfile_reports_not_running(self) -> None:
        stale_pid = _exited_pid()
        lifecycle_module._write_pidfile(stale_pid)
        assert status() == f"Daemon is not running (stale pidfile, pid {stale_pid})."


class TestStop:
    def test_no_pidfile_reports_nothing_to_stop(self) -> None:
        assert stop() == "No daemon pidfile found."

    def test_stale_pidfile_reports_no_process(self) -> None:
        stale_pid = _exited_pid()
        lifecycle_module._write_pidfile(stale_pid)
        assert stop() == f"No process running at pid {stale_pid} (stale pidfile)."

    def test_warns_about_a_managed_service_when_one_is_installed(self, mocker: MockerFixture) -> None:
        mocker.patch.object(lifecycle_module.service, "is_installed", return_value=True)
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
        try:
            lifecycle_module._write_pidfile(proc.pid)
            result = stop()
        finally:
            proc.wait(timeout=5)
        assert "cline-hook daemon service stop" in result

    def test_no_warning_when_no_service_is_installed(self, mocker: MockerFixture) -> None:
        mocker.patch.object(lifecycle_module.service, "is_installed", return_value=False)
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
        try:
            lifecycle_module._write_pidfile(proc.pid)
            result = stop()
        finally:
            proc.wait(timeout=5)
        assert "cline-hook daemon service stop" not in result


class TestEnsure:
    def test_does_nothing_when_a_daemon_already_answers(self, mocker: MockerFixture) -> None:
        mocker.patch.object(lifecycle_module, "probe_healthz", return_value={"pid": 1})
        spawn = mocker.patch.object(lifecycle_module, "spawn")

        ensure()

        spawn.assert_not_called()

    def test_spawns_when_nothing_answers(self, mocker: MockerFixture) -> None:
        mocker.patch.object(lifecycle_module, "probe_healthz", return_value=None)
        spawn = mocker.patch.object(lifecycle_module, "spawn")

        ensure()

        spawn.assert_called_once()


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
