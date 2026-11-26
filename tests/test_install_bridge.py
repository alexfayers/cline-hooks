"""Installer behaviour shared by the frontends that install a bridge script (pi, opencode)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from cline_hooks.frontends.opencode import OpencodeInstaller, OpencodeProtocol
from cline_hooks.frontends.pi import PiInstaller, PiProtocol

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from cline_hooks.core.protocol import Protocol

_EXPECTED_BINARY = str(Path("/fake/bin/cline-hook"))
_EMBEDDED = f"const BINARY: string = {json.dumps(_EXPECTED_BINARY)};"


class Bridge:
    """One frontend's bridge installer and where it writes."""

    def __init__(
        self,
        install: Callable[[], None],
        uninstall: Callable[[], None],
        path: Callable[[], Path],
        protocol: type[Protocol],
    ) -> None:
        self.install = install
        self.uninstall = uninstall
        self.path = path
        self.protocol = protocol

    def written(self) -> str:
        self.install()
        return self.path().read_text(encoding="utf-8")


@pytest.fixture(params=["pi", "opencode"])
def bridge(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Bridge]:
    """Yield a bridge installer writing under a throwaway home, with a resolved binary."""
    for name in ("PI_CODING_AGENT_DIR", "OPENCODE_CONFIG_DIR", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(name, raising=False)
    with (
        patch("cline_hooks.core.install.resolve_user_binary", return_value=Path(_EXPECTED_BINARY)),
        patch.object(Path, "home", return_value=tmp_path),
    ):
        if request.param == "pi":
            yield Bridge(
                lambda: PiInstaller().install(PiProtocol, None),
                lambda: PiInstaller().uninstall(PiProtocol, None),
                PiInstaller().extension_path,
                PiProtocol,
            )
        else:
            yield Bridge(
                lambda: OpencodeInstaller().install(OpencodeProtocol, None),
                lambda: OpencodeInstaller().uninstall(OpencodeProtocol, None),
                OpencodeInstaller().plugin_path,
                OpencodeProtocol,
            )


def _seed_embedded_binary(bridge: Bridge, binary: Path) -> None:
    """Install the bridge, then repoint its embedded binary at `binary`."""
    content = bridge.written()
    bridge.path().write_text(content.replace(json.dumps(_EXPECTED_BINARY), json.dumps(str(binary))), encoding="utf-8")


class TestBridgeInstaller:
    def test_embeds_the_resolved_binary_as_a_string_literal(self, bridge: Bridge) -> None:
        content = bridge.written()
        assert _EMBEDDED in content
        assert "__CLINE_HOOK_BINARY__" not in content

    def test_writes_nothing_where_there_is_no_user_wide_install(self, bridge: Bridge) -> None:
        with (
            patch("cline_hooks.core.install.resolve_user_binary", return_value=None),
            pytest.raises(SystemExit),
        ):
            bridge.install()
        assert not bridge.path().exists()

    def test_relays_every_registered_hook(self, bridge: Bridge) -> None:
        content = bridge.written()
        for registration in bridge.protocol.supported_hooks.values():
            assert f'hook_event_name: "{registration.native_name}"' in content

    def test_reinstall_is_idempotent(self, bridge: Bridge, capsys: pytest.CaptureFixture[str]) -> None:
        first = bridge.written()
        capsys.readouterr()
        assert bridge.written() == first
        assert "already up to date" in capsys.readouterr().out

    def test_repoints_an_embedded_binary_that_still_exists(self, bridge: Bridge, tmp_path: Path) -> None:
        working = tmp_path / "other-env" / "cline-hook"
        working.parent.mkdir()
        working.write_text("", encoding="utf-8")
        _seed_embedded_binary(bridge, working)
        assert _EMBEDDED in bridge.written()

    def test_repoints_an_embedded_binary_in_a_venv(self, bridge: Bridge, tmp_path: Path) -> None:
        venv_binary = tmp_path / "project" / ".venv" / "bin" / "cline-hook"
        venv_binary.parent.mkdir(parents=True)
        venv_binary.write_text("", encoding="utf-8")
        (tmp_path / "project" / ".venv" / "pyvenv.cfg").write_text("", encoding="utf-8")
        _seed_embedded_binary(bridge, venv_binary)
        assert _EMBEDDED in bridge.written()

    def test_replaces_an_embedded_binary_that_is_gone(self, bridge: Bridge, tmp_path: Path) -> None:
        _seed_embedded_binary(bridge, tmp_path / "gone" / "cline-hook")
        assert _EMBEDDED in bridge.written()

    def test_uninstall_removes_the_bridge(self, bridge: Bridge) -> None:
        bridge.install()
        bridge.uninstall()
        assert not bridge.path().exists()

    def test_uninstall_without_a_bridge_prints_one_line(
        self, bridge: Bridge, capsys: pytest.CaptureFixture[str]
    ) -> None:
        bridge.uninstall()
        assert len(capsys.readouterr().out.splitlines()) == 1
