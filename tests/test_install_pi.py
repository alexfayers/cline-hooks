from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from cline_hooks.frontends.pi import PiInstaller, PiProtocol

if TYPE_CHECKING:
    from collections.abc import Iterator

_EXPECTED_BINARY = str(Path("/fake/bin/cline-hook"))


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point Path.home() and the resolved binary at a throwaway directory.

    Yields:
        The fake home directory.
    """
    monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
    with (
        patch("cline_hooks.core.install.resolve_user_binary", return_value=Path(_EXPECTED_BINARY)),
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

    def test_listens_for_every_registered_hook(self, home: Path) -> None:
        content = _install()
        for registration in PiProtocol.supported_hooks.values():
            assert f'pi.on("{registration.native_name}"' in content

    def test_relays_the_child_identity(self, home: Path) -> None:
        content = _install()
        assert "agent_type: process.env.PI_HERDSMAN_AGENT_DEFINITION ?? process.env.PI_CONTEXT_ROLE" in content
        assert "agent_id: process.env.PI_HERDSMAN_RUN_ID ?? process.env.PI_CONTEXT_RUN_ID" in content

    def test_relays_the_context_usage_pi_reports(self, home: Path) -> None:
        content = _install()
        assert "context_window: usage?.contextWindow" in content
        assert "context_tokens: usage?.tokens" in content

    def test_relays_the_parent_tool_call_id_of_tool_events(self, home: Path) -> None:
        content = _install()
        assert content.count("parent_tool_call_id: event.parentToolCallId") == 2
