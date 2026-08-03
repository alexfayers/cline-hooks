from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from cline_hooks.frontends.copilot.install import _COPILOT_HOOKS, install_copilot

_FAKE_PYTHON = str(Path("/fake/bin/python"))


class TestInstallCopilot:
    @staticmethod
    def _expected_binary() -> str:
        return str(Path(_FAKE_PYTHON).parent / "cline-hook")

    def test_creates_hooks_file_when_missing(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.core.install.sys.executable", _FAKE_PYTHON),
            patch("cline_hooks.frontends.copilot.install.Path.home", return_value=tmp_path),
        ):
            install_copilot()

        hooks_path = tmp_path / ".copilot" / "hooks" / "cline-hooks.json"
        result = json.loads(hooks_path.read_text())
        assert set(result["hooks"].keys()) == set(_COPILOT_HOOKS)

    def test_hook_entries_have_type_and_command(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.core.install.sys.executable", _FAKE_PYTHON),
            patch("cline_hooks.frontends.copilot.install.Path.home", return_value=tmp_path),
        ):
            install_copilot()

        result = json.loads((tmp_path / ".copilot" / "hooks" / "cline-hooks.json").read_text())
        for event_name in _COPILOT_HOOKS:
            entry = result["hooks"][event_name][0]
            assert entry["type"] == "command"
            assert entry["command"] == self._expected_binary()

    def test_preserves_existing_fields(self, tmp_path: Path) -> None:
        hooks_dir = tmp_path / ".copilot" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "cline-hooks.json").write_text(json.dumps({"other": "value"}))

        with (
            patch("cline_hooks.core.install.sys.executable", _FAKE_PYTHON),
            patch("cline_hooks.frontends.copilot.install.Path.home", return_value=tmp_path),
        ):
            install_copilot()

        result = json.loads((hooks_dir / "cline-hooks.json").read_text())
        assert result["other"] == "value"
        assert "hooks" in result

    def test_preserves_entries_from_other_sources(self, tmp_path: Path) -> None:
        hooks_dir = tmp_path / ".copilot" / "hooks"
        hooks_dir.mkdir(parents=True)
        existing = {
            "hooks": {
                "SessionStart": [{"type": "command", "command": "/other/tool"}],
            },
        }
        (hooks_dir / "cline-hooks.json").write_text(json.dumps(existing))

        with (
            patch("cline_hooks.core.install.sys.executable", _FAKE_PYTHON),
            patch("cline_hooks.frontends.copilot.install.Path.home", return_value=tmp_path),
        ):
            install_copilot()

        result = json.loads((hooks_dir / "cline-hooks.json").read_text())
        commands = {entry["command"] for entry in result["hooks"]["SessionStart"]}
        assert "/other/tool" in commands
        assert self._expected_binary() in commands

    def test_idempotent_when_already_installed(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.core.install.sys.executable", _FAKE_PYTHON),
            patch("cline_hooks.frontends.copilot.install.Path.home", return_value=tmp_path),
        ):
            install_copilot()
            install_copilot()

        result = json.loads((tmp_path / ".copilot" / "hooks" / "cline-hooks.json").read_text())
        commands = [entry["command"] for entry in result["hooks"]["SessionStart"]]
        assert commands.count(self._expected_binary()) == 1
