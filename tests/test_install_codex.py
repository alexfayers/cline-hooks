from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from cline_hooks.frontends.codex.install import install_codex

_FAKE_PYTHON = str(Path("/fake/bin/python"))


class TestInstallCodex:
    @staticmethod
    def _expected_binary() -> str:
        return str(Path(_FAKE_PYTHON).parent / "cline-hook")

    def test_creates_hooks_json_when_missing(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.core.install.sys.executable", _FAKE_PYTHON),
            patch("cline_hooks.frontends.codex.install.Path.home", return_value=tmp_path),
        ):
            install_codex()

        hooks_path = tmp_path / ".codex" / "hooks.json"
        result = json.loads(hooks_path.read_text())
        assert set(result["hooks"].keys()) == {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"}

    def test_tool_hooks_have_matcher(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.core.install.sys.executable", _FAKE_PYTHON),
            patch("cline_hooks.frontends.codex.install.Path.home", return_value=tmp_path),
        ):
            install_codex()

        result = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
        assert result["hooks"]["PreToolUse"][0]["matcher"] == ""
        assert result["hooks"]["PostToolUse"][0]["matcher"] == ""
        assert "matcher" not in result["hooks"]["SessionStart"][0]

    def test_preserves_existing_fields(self, tmp_path: Path) -> None:
        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir()
        (codex_dir / "hooks.json").write_text(json.dumps({"other": "value"}))

        with (
            patch("cline_hooks.core.install.sys.executable", _FAKE_PYTHON),
            patch("cline_hooks.frontends.codex.install.Path.home", return_value=tmp_path),
        ):
            install_codex()

        result = json.loads((codex_dir / "hooks.json").read_text())
        assert result["other"] == "value"
        assert "hooks" in result

    def test_preserves_entries_from_other_sources(self, tmp_path: Path) -> None:
        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir()
        existing = {
            "hooks": {
                "SessionStart": [{"hooks": [{"type": "command", "command": "/other/tool"}]}],
            },
        }
        (codex_dir / "hooks.json").write_text(json.dumps(existing))

        with (
            patch("cline_hooks.core.install.sys.executable", _FAKE_PYTHON),
            patch("cline_hooks.frontends.codex.install.Path.home", return_value=tmp_path),
        ):
            install_codex()

        result = json.loads((codex_dir / "hooks.json").read_text())
        commands = {h["command"] for group in result["hooks"]["SessionStart"] for h in group["hooks"]}
        assert "/other/tool" in commands
        assert self._expected_binary() in commands

    def test_idempotent_when_already_installed(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.core.install.sys.executable", _FAKE_PYTHON),
            patch("cline_hooks.frontends.codex.install.Path.home", return_value=tmp_path),
        ):
            install_codex()
            install_codex()

        result = json.loads((tmp_path / ".codex" / "hooks.json").read_text())
        commands = {h["command"] for h in result["hooks"]["SessionStart"][0]["hooks"]}
        assert commands == {self._expected_binary()}
