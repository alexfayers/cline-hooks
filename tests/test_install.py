from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from cline_hooks.frontends.cline import (
    _HOOKS,
    install_cline as install,
)

if TYPE_CHECKING:
    import pytest


class TestInstall:
    _FAKE_PYTHON = str(Path("C:/fake/bin/python.exe"))

    @classmethod
    def _expected_binary(cls) -> str:
        return str(Path(cls._FAKE_PYTHON).parent / "cline-hook")

    @staticmethod
    def _normalize_link_target(path: str) -> str:
        path = path.removeprefix("\\\\?\\")
        return os.path.normcase(os.path.normpath(path))

    def test_prefers_existing_windows_binary(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "Scripts"
        scripts_dir.mkdir()
        exe = scripts_dir / "cline-hook.exe"
        exe.write_text("", encoding="utf-8")

        with (
            patch("cline_hooks.install.sys.executable", str(scripts_dir / "python.exe")),
            patch("cline_hooks.frontends.cline._is_windows", return_value=True),
        ):
            install(str(tmp_path / "hooks"))

        content = (tmp_path / "hooks" / f"{_HOOKS[0]}.ps1").read_text(encoding="utf-8")
        assert str(exe) in content

    def test_creates_target_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "hooks"
        with (
            patch("cline_hooks.install.sys.executable", self._FAKE_PYTHON),
            patch("cline_hooks.frontends.cline._is_windows", return_value=False),
        ):
            install(str(target))
        assert target.is_dir()

    def test_creates_symlinks_for_all_hooks(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.install.sys.executable", self._FAKE_PYTHON),
            patch("cline_hooks.frontends.cline._is_windows", return_value=False),
        ):
            install(str(tmp_path))
        for hook in _HOOKS:
            assert (tmp_path / hook).is_symlink()

    def test_symlinks_point_to_binary(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.install.sys.executable", self._FAKE_PYTHON),
            patch("cline_hooks.frontends.cline._is_windows", return_value=False),
        ):
            install(str(tmp_path))
        binary = self._expected_binary()
        for hook in _HOOKS:
            assert self._normalize_link_target(str((tmp_path / hook).readlink())) == self._normalize_link_target(binary)

    def test_skips_already_correct_symlinks(self, tmp_path: Path) -> None:
        binary = self._expected_binary()
        (tmp_path / _HOOKS[0]).symlink_to(binary)
        with (
            patch("cline_hooks.install.sys.executable", self._FAKE_PYTHON),
            patch("cline_hooks.frontends.cline._is_windows", return_value=False),
        ):
            install(str(tmp_path))
        assert self._normalize_link_target(str((tmp_path / _HOOKS[0]).readlink())) == self._normalize_link_target(
            binary
        )

    def test_skips_non_symlink_files(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        (tmp_path / _HOOKS[0]).write_text("existing file")
        with (
            patch("cline_hooks.install.sys.executable", self._FAKE_PYTHON),
            patch("cline_hooks.frontends.cline._is_windows", return_value=False),
        ):
            install(str(tmp_path))
        assert not (tmp_path / _HOOKS[0]).is_symlink()
        assert "skipping" in capsys.readouterr().err

    def test_replaces_stale_symlinks(self, tmp_path: Path) -> None:
        (tmp_path / _HOOKS[0]).symlink_to("stale-cline-hook")
        with (
            patch("cline_hooks.install.sys.executable", self._FAKE_PYTHON),
            patch("cline_hooks.frontends.cline._is_windows", return_value=False),
        ):
            install(str(tmp_path))
        binary = self._expected_binary()
        assert self._normalize_link_target(str((tmp_path / _HOOKS[0]).readlink())) == self._normalize_link_target(
            binary
        )

    def test_windows_writes_ps1_files_for_all_hooks(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.install.sys.executable", "C:/fake/Scripts/python.exe"),
            patch("cline_hooks.frontends.cline._is_windows", return_value=True),
        ):
            install(str(tmp_path))

        for hook in _HOOKS:
            script = tmp_path / f"{hook}.ps1"
            assert script.is_file()
            content = script.read_text(encoding="utf-8")
            assert "$inputData = [Console]::In.ReadToEnd()" in content

    def test_windows_skips_user_managed_script(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        script = tmp_path / f"{_HOOKS[0]}.ps1"
        script.write_text("Write-Host 'custom'\n", encoding="utf-8")

        with (
            patch("cline_hooks.install.sys.executable", "C:/fake/Scripts/python.exe"),
            patch("cline_hooks.frontends.cline._is_windows", return_value=True),
        ):
            install(str(tmp_path))

        assert script.read_text(encoding="utf-8") == "Write-Host 'custom'\n"
        assert "was not generated by cline-hook" in capsys.readouterr().err
