from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch


from cline_hooks.frontends.antigravity.install import install_antigravity

_FAKE_PYTHON = str(Path("/fake/bin/python"))


class TestInstallAntigravity:
    def test_creates_hooks_json_when_missing(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.core.install.sys.executable", _FAKE_PYTHON),
            patch("cline_hooks.frontends.antigravity.install.Path.home", return_value=tmp_path),
        ):
            hooks_path = install_antigravity()

        assert hooks_path == tmp_path / ".gemini" / "config" / "hooks.json"
        assert hooks_path.exists()
        result = json.loads(hooks_path.read_text())
        assert "cline-hooks" in result
        cline_hooks = result["cline-hooks"]
        assert "PreToolUse" in cline_hooks
        assert "PostToolUse" in cline_hooks
        assert "Stop" in cline_hooks

        pre = cline_hooks["PreToolUse"][0]
        assert pre["matcher"] == "*"
        assert "antigravity --event PreToolUse" in pre["hooks"][0]["command"]

    def test_preserves_existing_config(self, tmp_path: Path) -> None:
        gemini_dir = tmp_path / ".gemini" / "config"
        gemini_dir.mkdir(parents=True)
        (gemini_dir / "hooks.json").write_text(json.dumps({"other-tool": {"enabled": True}}))

        with (
            patch("cline_hooks.core.install.sys.executable", _FAKE_PYTHON),
            patch("cline_hooks.frontends.antigravity.install.Path.home", return_value=tmp_path),
        ):
            install_antigravity()

        result = json.loads((gemini_dir / "hooks.json").read_text())
        assert "other-tool" in result
        assert "cline-hooks" in result
