from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

import pytest

import cline_hooks.daemon.service as service_module
from cline_hooks.daemon.service import (
    MANAGED_MARKER,
    UnsupportedPlatformError,
    install,
    is_installed,
    status,
    stop,
    uninstall,
)

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import Mock

    from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def isolate_unit_paths(mocker: MockerFixture, tmp_path: Path) -> Mock:
    """Redirect both platforms' unit paths to tmp_path and stub out real subprocess calls.

    Never write to the real ~/Library/LaunchAgents or ~/.config/systemd, and
    never actually load/unload a unit into the running system.

    Returns:
        The mocked `subprocess.run`, so tests can inspect what it was called with.
    """
    mocker.patch.object(service_module, "_LAUNCHD_PLIST_PATH", tmp_path / "com.cline-hooks.daemon.plist")
    mocker.patch.object(service_module, "_SYSTEMD_UNIT_PATH", tmp_path / "cline-hooks-daemon.service")
    return mocker.patch.object(service_module.subprocess, "run", return_value=mocker.Mock(returncode=0, stderr=""))


class TestLaunchdContent:
    def test_has_the_managed_marker(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Darwin")
        install()
        content = service_module._LAUNCHD_PLIST_PATH.read_text(encoding="utf-8")
        assert MANAGED_MARKER in content

    def test_has_run_at_load(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Darwin")
        install()
        content = service_module._LAUNCHD_PLIST_PATH.read_text(encoding="utf-8")
        assert "<key>RunAtLoad</key>\n    <true/>" in content

    def test_has_unconditional_keep_alive(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Darwin")
        install()
        content = service_module._LAUNCHD_PLIST_PATH.read_text(encoding="utf-8")
        assert "<key>KeepAlive</key>\n    <true/>" in content

    def test_runs_daemon_serve(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Darwin")
        install()
        content = service_module._LAUNCHD_PLIST_PATH.read_text(encoding="utf-8")
        assert "<string>daemon</string>" in content
        assert "<string>serve</string>" in content


class TestSystemdContent:
    def test_has_the_managed_marker(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Linux")
        install()
        content = service_module._SYSTEMD_UNIT_PATH.read_text(encoding="utf-8")
        assert MANAGED_MARKER in content

    def test_has_restart_always(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Linux")
        install()
        content = service_module._SYSTEMD_UNIT_PATH.read_text(encoding="utf-8")
        assert "Restart=always" in content

    def test_has_wanted_by_default_target(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Linux")
        install()
        content = service_module._SYSTEMD_UNIT_PATH.read_text(encoding="utf-8")
        assert "WantedBy=default.target" in content

    def test_runs_daemon_serve(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Linux")
        install()
        content = service_module._SYSTEMD_UNIT_PATH.read_text(encoding="utf-8")
        assert "cline_hooks daemon serve" in content


class TestInstallIdempotency:
    def test_reinstalling_overwrites_in_place_not_duplicated(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Darwin")
        install()
        first_content = service_module._LAUNCHD_PLIST_PATH.read_text(encoding="utf-8")

        install()

        second_content = service_module._LAUNCHD_PLIST_PATH.read_text(encoding="utf-8")
        assert first_content == second_content
        assert service_module._LAUNCHD_PLIST_PATH.exists()

    def test_reinstalling_does_not_raise(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Linux")
        install()
        install()


class TestUninstall:
    def test_refuses_to_remove_a_foreign_file(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Darwin")
        service_module._LAUNCHD_PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        service_module._LAUNCHD_PLIST_PATH.write_text("some unrelated plist content", encoding="utf-8")

        with pytest.raises(RuntimeError, match="not written by cline-hooks"):
            uninstall()
        assert service_module._LAUNCHD_PLIST_PATH.exists()

    def test_removes_a_unit_it_installed(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Darwin")
        install()

        result = uninstall()

        assert not service_module._LAUNCHD_PLIST_PATH.exists()
        assert "Removed" in result

    def test_nothing_to_do_when_absent(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Linux")
        assert "nothing to do" in uninstall()


class TestServiceStop:
    def test_darwin_boots_out_via_the_supervisor(self, mocker: MockerFixture, isolate_unit_paths: Mock) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Darwin")
        install()
        isolate_unit_paths.reset_mock()

        result = stop()

        expected_target = f"gui/{os.getuid()}/{service_module._LAUNCHD_LABEL}"
        isolate_unit_paths.assert_called_once_with(
            [shutil.which("launchctl") or "launchctl", "bootout", expected_target],
            check=False,
            capture_output=True,
            text=True,
        )
        assert "Stopped" in result

    def test_linux_stops_via_systemctl(self, mocker: MockerFixture, isolate_unit_paths: Mock) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Linux")
        install()
        isolate_unit_paths.reset_mock()

        result = stop()

        isolate_unit_paths.assert_called_once_with(
            [shutil.which("systemctl") or "systemctl", "--user", "stop", service_module._SYSTEMD_UNIT_NAME],
            check=False,
            capture_output=True,
            text=True,
        )
        assert "Stopped" in result

    def test_nothing_installed_reports_nothing_to_stop(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Darwin")
        assert "nothing to stop" in stop()

    def test_does_not_stop_a_foreign_file(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Darwin")
        service_module._LAUNCHD_PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        service_module._LAUNCHD_PLIST_PATH.write_text("unrelated content", encoding="utf-8")

        assert "nothing to stop" in stop()


class TestIsInstalled:
    def test_true_after_install(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Darwin")
        install()
        assert is_installed() is True

    def test_false_when_absent(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Linux")
        assert is_installed() is False

    def test_false_for_a_foreign_file(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Darwin")
        service_module._LAUNCHD_PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        service_module._LAUNCHD_PLIST_PATH.write_text("unrelated content", encoding="utf-8")
        assert is_installed() is False

    def test_false_on_an_unsupported_platform(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Windows")
        assert is_installed() is False


class TestUnsupportedPlatform:
    def test_install_raises(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Windows")
        with pytest.raises(UnsupportedPlatformError):
            install()

    def test_uninstall_raises(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Windows")
        with pytest.raises(UnsupportedPlatformError):
            uninstall()

    def test_stop_raises(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Windows")
        with pytest.raises(UnsupportedPlatformError):
            stop()

    def test_status_reports_rather_than_raising(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Windows")
        assert "No supported service supervisor" in status()
