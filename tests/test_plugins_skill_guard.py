from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.protocol import set_protocol
from cline_hooks.core.vocabulary import PluginScope
from cline_hooks.frontends.claude_code.protocol import ClaudeCodeProtocol
from cline_hooks.frontends.pi.protocol import PiProtocol
from cline_hooks.plugins.skill_guard import SkillGuardPlugin
from cline_hooks.state.skills import record_skill
from tests.conftest import UNSUPPORTED_SYNTAX

if TYPE_CHECKING:
    from pathlib import Path

    from cline_hooks.core.plugin import HookResult


def _pre_shell(command: str, agent_id: str | None = None) -> HookResult | None:
    return SkillGuardPlugin().on_hook(
        PluginScope.PRE_SHELL,
        logger=logging.getLogger("test"),
        command=command,
        task_id=f"t:{agent_id}" if agent_id else "t",
        agent_id=agent_id,
    )


@pytest.mark.parametrize("command", UNSUPPORTED_SYNTAX)
def test_allows_a_command_bashlex_cannot_parse(command: str) -> None:
    assert _pre_shell(command) is None


class TestSkillGuard:
    @pytest.mark.parametrize("agent_id", [None, "a1"])
    @pytest.mark.parametrize("command", ["git status", "git -P log --oneline", "git diff && git rev-parse HEAD"])
    def test_allows_read_only_git_for_everyone(self, command: str, agent_id: str | None) -> None:
        assert _pre_shell(command, agent_id=agent_id) is None

    @pytest.mark.parametrize("agent_id", [None, "a1"])
    @pytest.mark.parametrize("command", ["git status && git commit -m x", "git -C /x commit -m x"])
    def test_blocks_other_git_for_everyone(self, command: str, agent_id: str | None) -> None:
        result = _pre_shell(command, agent_id=agent_id)
        assert result is not None
        assert result.block is not None
        assert "git-usage" in result.block

    @pytest.mark.parametrize("agent_id", [None, "a1"])
    def test_allows_git_commit_after_the_skill(self, agent_id: str | None) -> None:
        record_skill(f"t:{agent_id}" if agent_id else "t", "git-usage")
        assert _pre_shell("git commit -m x", agent_id=agent_id) is None


class TestSkillPathInBlock:
    def test_pi_block_names_the_existing_skill_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        skill = tmp_path / "skills" / "git-usage" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("x")
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
        set_protocol(PiProtocol())
        result = _pre_shell("git commit -m x")
        assert result is not None
        assert result.block == f"MUST use the `git-usage` skill before running this command - read {skill} first"

    def test_pi_block_without_the_skill_file_keeps_the_plain_text(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
        set_protocol(PiProtocol())
        result = _pre_shell("git commit -m x")
        assert result is not None
        assert result.block == "MUST use the `git-usage` skill before running this command"

    def test_claude_block_names_the_home_skill_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        skill = tmp_path / ".claude" / "skills" / "git-usage" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("x")
        set_protocol(ClaudeCodeProtocol())
        result = _pre_shell("git commit -m x")
        assert result is not None
        assert result.block is not None
        assert str(skill) in result.block
