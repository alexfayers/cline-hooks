from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from cline_hooks.frontends.opencode import OpencodeInstaller, OpencodeProtocol

if TYPE_CHECKING:
    from collections.abc import Iterator

_EXPECTED_BINARY = str(Path("/fake/bin/cline-hook"))


@pytest.fixture
def home(tmp_path: Path) -> Iterator[Path]:
    """Point Path.home() and the resolved binary at a throwaway directory.

    Yields:
        The fake home directory.
    """
    with (
        patch("cline_hooks.core.install.resolve_user_binary", return_value=Path(_EXPECTED_BINARY)),
        patch.object(Path, "home", return_value=tmp_path),
    ):
        yield tmp_path


def _install() -> str:
    """Run the opencode installer and read back the plugin it wrote.

    Returns:
        The written plugin source.
    """
    installer = OpencodeInstaller()
    installer.install(OpencodeProtocol, None)
    return installer.plugin_path().read_text(encoding="utf-8")


class TestOpencodeInstaller:
    def test_writes_into_the_global_plugins_directory(self, home: Path) -> None:
        _install()
        assert (home / ".config" / "opencode" / "plugins" / "cline-hooks.ts").is_file()

    def test_embeds_the_resolved_binary_as_a_string_literal(self, home: Path) -> None:
        content = _install()
        assert f"const BINARY: string = {json.dumps(_EXPECTED_BINARY)};" in content
        assert "__CLINE_HOOK_BINARY__" not in content

    def test_rerun_leaves_an_up_to_date_plugin(self, home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        first = _install()
        assert _install() == first
        assert "already up to date" in capsys.readouterr().out

    def test_relays_every_registered_hook(self, home: Path) -> None:
        content = _install()
        for registration in OpencodeProtocol.supported_hooks.values():
            assert f'hook_event_name: "{registration.native_name}"' in content
