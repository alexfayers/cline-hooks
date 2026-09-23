from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from cline_hooks.frontends.pi import PiInstaller, PiProtocol

if TYPE_CHECKING:
    from collections.abc import Iterator

_FAKE_PYTHON = str(Path("/fake/bin/python"))
_EXPECTED_BINARY = str(Path(_FAKE_PYTHON).parent / "cline-hook")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point Path.home() and the resolved binary at a throwaway directory.

    Yields:
        The fake home directory.
    """
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    with (
        patch("cline_hooks.core.install.sys.executable", _FAKE_PYTHON),
        patch.object(Path, "home", return_value=tmp_path),
    ):
        yield tmp_path


def _install() -> str:
    """Run the pi installer and read back the extension it wrote.

    Returns:
        The written extension source.
    """
    installer = PiInstaller()
    installer.install(PiProtocol, None)
    return installer.extension_path().read_text(encoding="utf-8")


class TestPiInstaller:
    def test_writes_into_the_global_extensions_directory(self, home: Path) -> None:
        _install()
        assert (home / ".pi" / "agent" / "extensions" / "cline-hooks.ts").is_file()

    def test_honours_the_agent_dir_override(self, home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(home / "custom"))
        _install()
        assert (home / "custom" / "extensions" / "cline-hooks.ts").is_file()

    def test_embeds_the_resolved_binary_as_a_string_literal(self, home: Path) -> None:
        content = _install()
        assert f"const BINARY: string = {json.dumps(_EXPECTED_BINARY)};" in content
        assert "__CLINE_HOOK_BINARY__" not in content

    def test_relays_every_registered_hook(self, home: Path) -> None:
        content = _install()
        for registration in PiProtocol.supported_hooks.values():
            assert f'pi.on("{registration.native_name}"' in content
            assert f'hook_event_name: "{registration.native_name}"' in content

    def test_reinstall_is_idempotent(self, home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        first = _install()
        capsys.readouterr()
        assert _install() == first
        assert "already up to date" in capsys.readouterr().out
