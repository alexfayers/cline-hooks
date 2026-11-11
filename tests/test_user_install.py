from __future__ import annotations

import os
from typing import TYPE_CHECKING

from cline_hooks.core.user_install import DEV_BIN_DIR_ENV, resolve_user_binary, user_path

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _make_dir(root: Path, name: str, *, venv: bool, binary: str | None = "tool") -> Path:
    """Build `<root>/<name>/bin`, with a binary and a venv marker as asked.

    Returns:
        The bin directory.
    """
    bin_dir = root / name / "bin"
    bin_dir.mkdir(parents=True)
    if venv:
        (root / name / "pyvenv.cfg").write_text("", encoding="utf-8")
    if binary:
        executable = bin_dir / binary
        executable.write_text("", encoding="utf-8")
        executable.chmod(0o755)
    return bin_dir


def _set_path(monkeypatch: pytest.MonkeyPatch, *directories: Path) -> None:
    monkeypatch.setenv("PATH", os.pathsep.join(str(directory) for directory in directories))
    monkeypatch.delenv("CLINE_HOOKS_DEV_BIN_DIR", raising=False)


class TestResolveUserBinary:
    def test_skips_a_venv_directory_ahead_of_the_user_install(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        venv = _make_dir(tmp_path, "venv", venv=True)
        user = _make_dir(tmp_path, "user", venv=False)
        _set_path(monkeypatch, venv, user)
        assert resolve_user_binary("tool") == user / "tool"

    def test_none_where_only_a_venv_has_the_binary(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_path(monkeypatch, _make_dir(tmp_path, "venv", venv=True))
        assert resolve_user_binary("tool") is None

    def test_skips_a_link_to_a_venv_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        venv = _make_dir(tmp_path, "venv", venv=True)
        link = tmp_path / "home" / "bin"
        link.parent.mkdir()
        link.symlink_to(venv)
        _set_path(monkeypatch, link)
        assert resolve_user_binary("tool") is None

    def test_keeps_the_link_path_rather_than_its_target(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        target = _make_dir(tmp_path, "store", venv=False) / "tool"
        user = _make_dir(tmp_path, "user", venv=False, binary=None)
        (user / "tool").symlink_to(target)
        _set_path(monkeypatch, user)
        assert resolve_user_binary("tool") == user / "tool"

    def test_dev_directory_wins_even_when_a_venv_and_warns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        dev = _make_dir(tmp_path, "dev", venv=True)
        _set_path(monkeypatch, _make_dir(tmp_path, "user", venv=False))
        monkeypatch.setenv(DEV_BIN_DIR_ENV, str(dev))
        assert resolve_user_binary("tool") == dev / "tool"
        assert str(dev) in capsys.readouterr().err


class TestUserPath:
    def test_drops_venv_directories_keeps_order_and_leads_with_the_dev_directory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first = _make_dir(tmp_path, "first", venv=False)
        venv = _make_dir(tmp_path, "venv", venv=True)
        second = _make_dir(tmp_path, "second", venv=False)
        assert user_path(os.pathsep.join(map(str, (first, venv, second)))) == os.pathsep.join(map(str, (first, second)))
        monkeypatch.setenv(DEV_BIN_DIR_ENV, str(venv))
        assert user_path(str(first)) == os.pathsep.join(map(str, (venv, first)))
