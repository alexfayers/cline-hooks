from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from cline_hooks.frontends.opencode import OpencodeInstaller, OpencodeProtocol

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point Path.home() and the resolved binary at a throwaway directory.

    Yields:
        The fake home directory.
    """
    monkeypatch.delenv("OPENCODE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    with (
        patch("cline_hooks.core.install.resolve_user_binary", return_value=Path("/fake/bin/cline-hook")),
        patch.object(Path, "home", return_value=tmp_path),
    ):
        yield tmp_path


class TestOpencodeInstaller:
    def test_writes_into_the_global_plugins_directory(self, home: Path) -> None:
        OpencodeInstaller().install(OpencodeProtocol, None)
        assert (home / ".config" / "opencode" / "plugins" / "cline-hooks.ts").is_file()

    def test_honours_the_opencode_config_dir(self, home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(home / "custom"))
        OpencodeInstaller().install(OpencodeProtocol, None)
        assert (home / "custom" / "plugins" / "cline-hooks.ts").is_file()
