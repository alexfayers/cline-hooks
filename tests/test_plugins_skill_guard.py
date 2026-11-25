from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.protocol import set_protocol
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool, PluginScope
from cline_hooks.frontends.antigravity.protocol import AntigravityProtocol
from cline_hooks.frontends.claude_code.protocol import ClaudeCodeProtocol
from cline_hooks.frontends.codex.protocol import CodexProtocol
from cline_hooks.frontends.kiro.protocol import KiroProtocol
from cline_hooks.frontends.pi.protocol import PiProtocol
from cline_hooks.plugins.skill_guard import SkillGuardPlugin
from cline_hooks.state.skills import record_skill
from tests.conftest import UNSUPPORTED_SYNTAX

if TYPE_CHECKING:
    from pathlib import Path

    from cline_hooks.core.plugin import HookResult
    from cline_hooks.core.protocol import Protocol


def _pre_shell(command: str, agent_id: str | None = None) -> HookResult | None:
    return SkillGuardPlugin().on_hook(
        PluginScope.PRE_SHELL,
        logger=logging.getLogger("test"),
        command=command,
        task_id=f"t:{agent_id}" if agent_id else "t",
        agent_id=agent_id,
    )


def _allowed(tool_name: CanonicalTool, parameters: dict[str, object]) -> None:
    SkillGuardPlugin().on_hook(
        PluginScope.TOOL_ALLOWED,
        logger=logging.getLogger("test"),
        task_id="t",
        tool_name=tool_name,
        parameters=parameters,
        workspace_roots=[],
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
    def test_pi_adds_the_installed_skill_text_and_allows_the_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        skill = tmp_path / "skills" / "git-usage" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("use git carefully")
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
        set_protocol(PiProtocol())
        result = _pre_shell("git commit -m x")
        assert result is not None
        assert result.block is None
        assert result.notes == ["REQUIRED: the `git-usage` skill:\n\nuse git carefully"]

    def test_adds_the_skill_text_only_once_per_session(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        skill = tmp_path / "skills" / "git-usage" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("x")
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
        set_protocol(PiProtocol())
        assert _pre_shell("git commit -m x") is not None
        _allowed(CanonicalTool.SHELL, {"command": "git commit -m x"})
        assert _pre_shell("git commit -m y") is None

    def test_adds_the_skill_text_again_after_a_blocked_attempt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        skill = tmp_path / "skills" / "git-usage" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("x")
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
        set_protocol(PiProtocol())
        first = _pre_shell("git commit -m x")
        assert first is not None
        assert first.notes
        retry = _pre_shell("git commit -m x")
        assert retry is not None
        assert retry.notes == first.notes
        _allowed(CanonicalTool.SHELL, {"command": "git commit -m x"})
        assert _pre_shell("git commit -m x") is None

    def test_pi_block_without_the_skill_file_keeps_the_plain_text(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
        set_protocol(PiProtocol())
        result = _pre_shell("git commit -m x")
        assert result is not None
        assert result.block == "MUST use the `git-usage` skill before running this command"

    def test_claude_adds_the_home_skill_text(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        skill = tmp_path / ".claude" / "skills" / "git-usage" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("claude skill text")
        set_protocol(ClaudeCodeProtocol())
        result = _pre_shell("git commit -m x")
        assert result is not None
        assert result.block is None
        assert "claude skill text" in result.notes[0]

    @pytest.mark.parametrize(
        ("protocol", "skills"),
        [
            (KiroProtocol, ".kiro/skills"),
            (CodexProtocol, ".codex/skills"),
            (AntigravityProtocol, ".gemini/config/skills"),
        ],
    )
    def test_home_frontend_adds_the_home_skill_text(
        self, protocol: type[Protocol], skills: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        skill = tmp_path / skills / "git-usage" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("home skill text")
        set_protocol(protocol())
        result = _pre_shell("git commit -m x")
        assert result is not None
        assert result.block is None
        assert "home skill text" in result.notes[0]


@pytest.fixture
def pi_skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    set_protocol(PiProtocol())
    for relative in (
        "git-usage/SKILL.md",
        "git-usage/tidy.md",
        "llm-prompts/setup.md",
        "llm-prompts/contribute.md",
        "llm-prompts/edit.md",
    ):
        skill_file = tmp_path / "skills" / relative
        skill_file.parent.mkdir(parents=True, exist_ok=True)
        skill_file.write_text("x")
    return tmp_path / "skills"


def _pre_edit(path: object, workspace_roots: list[str] | None = None) -> HookResult | None:
    return SkillGuardPlugin().on_hook(
        CanonicalHook.PRE_TOOL_USE,
        logger=logging.getLogger("test"),
        task_id="t",
        tool_name=CanonicalTool.EDIT,
        parameters={"path": path},
        workspace_roots=workspace_roots or [],
    )


TIDY_REBASE = "GIT_SEQUENCE_EDITOR=: git rebase -i --autosquash main"


class TestSkillPartGuard:
    def test_tidy_rebase_adds_the_part_text_once(self, pi_skills: Path) -> None:
        record_skill("t", "git-usage")
        result = _pre_shell(TIDY_REBASE)
        assert result is not None
        assert result.block is None
        assert len(result.notes) == 1
        assert "`git-usage/tidy.md`" in result.notes[0]
        _allowed(CanonicalTool.SHELL, {"command": TIDY_REBASE})
        assert _pre_shell(TIDY_REBASE) is None

    def test_adds_every_missing_requirement(self, pi_skills: Path) -> None:
        result = _pre_shell(TIDY_REBASE)
        assert result is not None
        assert result.block is None
        assert len(result.notes) == 2
        assert "`git-usage`" in result.notes[0]
        assert "`git-usage/tidy.md`" in result.notes[1]
        _allowed(CanonicalTool.SHELL, {"command": TIDY_REBASE})
        assert _pre_shell(TIDY_REBASE) is None

    def test_blocks_when_one_missing_requirement_is_not_installed(self, pi_skills: Path) -> None:
        (pi_skills / "git-usage" / "SKILL.md").unlink()
        result = _pre_shell(TIDY_REBASE)
        assert result is not None
        assert result.block == (
            "MUST use the `git-usage` skill and the `git-usage/tidy.md` skill part before running this command"
            f" - read {pi_skills / 'git-usage' / 'tidy.md'} first"
        )

    def test_tidy_rebase_needs_only_the_skill_when_the_part_is_not_installed(self, pi_skills: Path) -> None:
        (pi_skills / "git-usage" / "tidy.md").unlink()
        record_skill("t", "git-usage")
        assert _pre_shell(TIDY_REBASE) is None

    def test_other_rebases_need_only_the_skill(self, pi_skills: Path) -> None:
        record_skill("t", "git-usage")
        assert _pre_shell("git rebase origin/main") is None

    @pytest.mark.parametrize(
        ("command", "part"),
        [
            ("llm-prompts setup", "setup.md"),
            ("HOME=/tmp/h llm-prompts install pi", "setup.md"),
            ("llm-prompts contribute sync", "contribute.md"),
        ],
    )
    def test_llm_prompts_commands_add_their_part(self, pi_skills: Path, command: str, part: str) -> None:
        result = _pre_shell(command)
        assert result is not None
        assert result.block is None
        assert f"`llm-prompts/{part}`" in result.notes[0]

    @pytest.mark.parametrize("command", ["llm-prompts update", "llm-prompts contribute list"])
    def test_routine_llm_prompts_commands_are_allowed(self, pi_skills: Path, command: str) -> None:
        assert _pre_shell(command) is None

    @pytest.mark.parametrize(
        ("path", "part"),
        [
            ("src/llm_prompts/prompts/shared/rules/git.md", "edit.md"),
            ("/h/.config/llm-prompts/config.toml", "setup.md"),
        ],
    )
    def test_prompt_source_and_config_edits_add_their_part(self, pi_skills: Path, path: str, part: str) -> None:
        result = _pre_edit(path)
        assert result is not None
        assert result.block is None
        assert result.notes == [f"REQUIRED: the `llm-prompts/{part}` skill:\n\nx"]
        _allowed(CanonicalTool.EDIT, {"path": path})
        assert _pre_edit(path) is None

    @pytest.mark.parametrize(
        ("path", "cwd", "part"),
        [
            ("rules/example.md", "/src/llm_prompts/prompts/shared", "edit.md"),
            ("../skills/x/SKILL.md", "/src/llm_prompts/prompts/shared/rules", "edit.md"),
            ("config.toml", "/h/.config/llm-prompts", "setup.md"),
        ],
    )
    def test_relative_edits_resolve_against_the_working_directory(
        self, pi_skills: Path, path: str, cwd: str, part: str
    ) -> None:
        result = _pre_edit(path, [cwd])
        assert result is not None
        assert result.block is None
        assert f"`llm-prompts/{part}`" in result.notes[0]

    def test_relative_edit_elsewhere_is_allowed(self, pi_skills: Path) -> None:
        assert _pre_edit("config.toml", ["/work/app"]) is None

    @pytest.mark.parametrize("path", [None, 5])
    def test_edit_without_a_string_path_is_allowed(self, pi_skills: Path, path: object) -> None:
        _allowed(CanonicalTool.EDIT, {"path": path})
        assert _pre_edit(path) is None

    def test_other_edits_are_allowed(self, pi_skills: Path) -> None:
        assert _pre_edit("src/app/rules.py") is None
