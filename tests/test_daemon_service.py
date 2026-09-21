from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import cline_hooks.daemon.service as service_module
from cline_hooks.daemon.service import UnsupportedPlatformError, install, is_installed, status, stop, uninstall

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path
    from unittest.mock import Mock

    from pytest_mock import MockerFixture

_UNIT_PATH_ATTRS = {"Darwin": "_LAUNCHD_PLIST_PATH", "Linux": "_SYSTEMD_UNIT_PATH"}


@pytest.fixture(autouse=True)
def supervisor(mocker: MockerFixture, tmp_path: Path) -> Mock:
    """Redirect both platforms' unit paths to tmp_path and stub out subprocess calls.

    Returns:
        The mocked `subprocess.run`.
    """
    for attr in _UNIT_PATH_ATTRS.values():
        mocker.patch.object(service_module, attr, tmp_path / attr)
    return mocker.patch.object(service_module.subprocess, "run", return_value=mocker.Mock(returncode=0, stderr=""))


@pytest.fixture(params=list(_UNIT_PATH_ATTRS))
def unit_path(request: pytest.FixtureRequest, mocker: MockerFixture, supervisor: Mock) -> Path:
    """Run on each supported platform.

    Returns:
        That platform's unit file path.
    """
    mocker.patch.object(service_module.platform, "system", return_value=request.param)
    path: Path = getattr(service_module, _UNIT_PATH_ATTRS[request.param])
    return path


@pytest.fixture(params=["absent", "foreign"])
def not_ours(request: pytest.FixtureRequest, unit_path: Path) -> Path:
    """Leave the unit path empty, or fill it with a file cline-hooks did not write.

    Returns:
        The unit file path.
    """
    if request.param == "foreign":
        unit_path.write_text("unrelated content", encoding="utf-8")
    return unit_path


class TestInstall:
    def test_installs_a_unit_it_recognises(self, unit_path: Path) -> None:
        install()
        assert is_installed()

    def test_not_installed_without_our_unit(self, not_ours: Path) -> None:
        assert not is_installed()


class TestUninstall:
    def test_removes_a_unit_it_installed(self, unit_path: Path) -> None:
        install()
        assert "Removed" in uninstall()
        assert not unit_path.exists()

    def test_nothing_to_do_when_absent(self, unit_path: Path) -> None:
        assert "nothing to do" in uninstall()

    def test_refuses_to_remove_a_foreign_file(self, unit_path: Path) -> None:
        unit_path.write_text("unrelated content", encoding="utf-8")
        with pytest.raises(RuntimeError, match="not written by cline-hooks"):
            uninstall()
        assert unit_path.exists()


class TestStop:
    def test_stops_through_the_supervisor(self, unit_path: Path, supervisor: Mock) -> None:
        install()
        supervisor.reset_mock()
        assert "Stopped" in stop()
        supervisor.assert_called_once()

    def test_nothing_to_stop_without_our_unit(self, not_ours: Path, supervisor: Mock) -> None:
        assert "nothing to stop" in stop()
        supervisor.assert_not_called()


class TestUnsupportedPlatform:
    @pytest.fixture(autouse=True)
    def windows(self, mocker: MockerFixture) -> None:
        mocker.patch.object(service_module.platform, "system", return_value="Windows")

    @pytest.mark.parametrize("action", [install, uninstall, stop])
    def test_actions_raise(self, action: Callable[[], str]) -> None:
        with pytest.raises(UnsupportedPlatformError):
            action()

    def test_queries_report_rather_than_raise(self) -> None:
        assert not is_installed()
        assert "No supported service supervisor" in status()
