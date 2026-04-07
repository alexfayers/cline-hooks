from __future__ import annotations

import json
from pathlib import Path

from cline_hooks.frontends.kiro import _build_kiro_hooks, install_kiro


class TestBuildKiroHooks:
    def test_has_all_hooks(self) -> None:
        hooks = _build_kiro_hooks(Path("/usr/bin/cline-hook"))
        assert set(hooks.keys()) == {"agentSpawn", "userPromptSubmit", "preToolUse", "postToolUse", "stop"}

    def test_tool_hooks_have_matcher(self) -> None:
        hooks = _build_kiro_hooks(Path("/usr/bin/cline-hook"))
        assert hooks["preToolUse"][0]["matcher"] == "*"
        assert hooks["postToolUse"][0]["matcher"] == "*"

    def test_non_tool_hooks_no_matcher(self) -> None:
        hooks = _build_kiro_hooks(Path("/usr/bin/cline-hook"))
        assert "matcher" not in hooks["agentSpawn"][0]
        assert "matcher" not in hooks["userPromptSubmit"][0]
        assert "matcher" not in hooks["stop"][0]

    def test_command_is_binary_path(self) -> None:
        hooks = _build_kiro_hooks(Path("/usr/bin/cline-hook"))
        for entries in hooks.values():
            assert entries[0]["command"] == "/usr/bin/cline-hook"


class TestInstallKiro:
    def test_patches_agent_config(self, tmp_path: Path) -> None:
        config = {"name": "test-agent", "tools": ["*"]}
        config_path = tmp_path / "agent.json"
        config_path.write_text(json.dumps(config))

        install_kiro(str(config_path))

        result = json.loads(config_path.read_text())
        assert "hooks" in result
        assert "name" in result
        assert set(result["hooks"].keys()) == {"agentSpawn", "userPromptSubmit", "preToolUse", "postToolUse", "stop"}

    def test_preserves_existing_fields(self, tmp_path: Path) -> None:
        config = {"name": "my-agent", "description": "test", "tools": ["fs_read"]}
        config_path = tmp_path / "agent.json"
        config_path.write_text(json.dumps(config))

        install_kiro(str(config_path))

        result = json.loads(config_path.read_text())
        assert result["name"] == "my-agent"
        assert result["description"] == "test"
        assert result["tools"] == ["fs_read"]
