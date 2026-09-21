from __future__ import annotations

import json
from pathlib import Path
import re
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from cline_hooks.frontends.pi import PiInstaller, PiProtocol

if TYPE_CHECKING:
    from collections.abc import Iterator

_FAKE_PYTHON = str(Path("/fake/bin/python"))
_BIN_DIR = Path(_FAKE_PYTHON).parent
_GUARDED_EVENTS = ("before_agent_start", "tool_call", "tool_result", "agent_end")
_EXPECTED_BINARIES = {
    registration.native_name: str(
        _BIN_DIR / ("cline-hook-guard" if registration.native_name in _GUARDED_EVENTS else "cline-hook")
    )
    for registration in PiProtocol.supported_hooks.values()
}


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


def _install(*, force: bool = False) -> str:
    """Run the pi installer and read back the extension it wrote.

    Returns:
        The written extension source.
    """
    installer = PiInstaller()
    installer.install(PiProtocol, None, force=force)
    return installer.extension_path().read_text(encoding="utf-8")


def _embedded_binaries(content: str) -> dict[str, str]:
    """Read the event-to-binary map embedded in an installed extension.

    Returns:
        The map, keyed by native event name.
    """
    match = re.search(r"const BINARIES: Record<string, string> = (\{.*\});", content)
    assert match
    return dict(json.loads(match.group(1)))


def _seed_embedded_binary(binary: Path) -> None:
    """Install the extension, then repoint its embedded `cline-hook` binary at `binary`."""
    content = _install()
    PiInstaller().extension_path().write_text(
        content.replace(json.dumps(str(_BIN_DIR / "cline-hook")), json.dumps(str(binary))), encoding="utf-8"
    )


class TestPiInstaller:
    def test_writes_into_the_global_extensions_directory(self, home: Path) -> None:
        _install()
        assert (home / ".pi" / "agent" / "extensions" / "cline-hooks.ts").is_file()

    def test_honours_the_agent_dir_override(self, home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(home / "custom"))
        _install()
        assert (home / "custom" / "extensions" / "cline-hooks.ts").is_file()

    def test_embeds_the_guard_for_relayed_events_and_cline_hook_for_the_rest(self, home: Path) -> None:
        content = _install()
        assert _embedded_binaries(content) == _EXPECTED_BINARIES
        assert "__CLINE_HOOK_BINARY__" not in content

    def test_relays_every_registered_hook(self, home: Path) -> None:
        content = _install()
        for registration in PiProtocol.supported_hooks.values():
            assert f'pi.on("{registration.native_name}"' in content
            assert f'hook_event_name: "{registration.native_name}"' in content

    def test_relays_the_herdsman_child_identity(self, home: Path) -> None:
        content = _install()
        assert 'agent_type: process.env.PI_HERDSMAN_AGENT_DEFINITION ?? ""' in content
        assert 'agent_id: process.env.PI_HERDSMAN_RUN_ID ?? ""' in content

    def test_relays_the_context_usage_pi_reports(self, home: Path) -> None:
        content = _install()
        assert "context_window: usage?.contextWindow" in content
        assert "context_tokens: usage?.tokens" in content

    def test_relays_the_parent_tool_call_id_of_tool_events(self, home: Path) -> None:
        content = _install()
        assert content.count("parent_tool_call_id: event.parentToolCallId") == 2

    def test_reinstall_is_idempotent(self, home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        first = _install()
        capsys.readouterr()
        assert _install() == first
        assert "already up to date" in capsys.readouterr().out

    def test_repoints_an_embedded_binary_that_still_exists(self, home: Path) -> None:
        working = home / "other-env" / "cline-hook"
        working.parent.mkdir()
        working.write_text("", encoding="utf-8")
        _seed_embedded_binary(working)
        assert _embedded_binaries(_install()) == _EXPECTED_BINARIES

    def test_replaces_an_embedded_binary_that_is_gone(self, home: Path) -> None:
        _seed_embedded_binary(home / "gone" / "cline-hook")
        assert _embedded_binaries(_install()) == _EXPECTED_BINARIES
