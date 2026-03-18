from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from cline_hooks.install import install, _HOOKS


class TestInstall:
    def test_creates_target_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "hooks"
        with patch("cline_hooks.install.sys.executable", "/fake/bin/python"):
            install(str(target))
        assert target.is_dir()

    def test_creates_symlinks_for_all_hooks(self, tmp_path: Path) -> None:
        with patch("cline_hooks.install.sys.executable", "/fake/bin/python"):
            install(str(tmp_path))
        for hook in _HOOKS:
            assert (tmp_path / hook).is_symlink()

    def test_symlinks_point_to_binary(self, tmp_path: Path) -> None:
        with patch("cline_hooks.install.sys.executable", "/fake/bin/python"):
            install(str(tmp_path))
        binary = str(Path("/fake/bin") / "cline-hook")
        for hook in _HOOKS:
            import os

            assert os.readlink(str(tmp_path / hook)) == binary

    def test_skips_already_correct_symlinks(self, tmp_path: Path) -> None:
        import os

        binary = str(Path("/fake/bin") / "cline-hook")
        (tmp_path / _HOOKS[0]).symlink_to(binary)
        with patch("cline_hooks.install.sys.executable", "/fake/bin/python"):
            install(str(tmp_path))
        assert os.readlink(str(tmp_path / _HOOKS[0])) == binary

    def test_skips_non_symlink_files(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / _HOOKS[0]).write_text("existing file")
        with patch("cline_hooks.install.sys.executable", "/fake/bin/python"):
            install(str(tmp_path))
        assert not (tmp_path / _HOOKS[0]).is_symlink()
        assert "skipping" in capsys.readouterr().err

    def test_replaces_stale_symlinks(self, tmp_path: Path) -> None:
        import os

        (tmp_path / _HOOKS[0]).symlink_to("/old/path/cline-hook")
        with patch("cline_hooks.install.sys.executable", "/fake/bin/python"):
            install(str(tmp_path))
        binary = str(Path("/fake/bin") / "cline-hook")
        assert os.readlink(str(tmp_path / _HOOKS[0])) == binary
