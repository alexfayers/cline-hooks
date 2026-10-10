from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.protocol import set_protocol
from cline_hooks.core.vocabulary import PluginScope
from cline_hooks.frontends.claude_code.protocol import ClaudeCodeProtocol
from cline_hooks.frontends.pi.protocol import PiProtocol
from cline_hooks.plugins.shell_guards import ShellGuardsPlugin
from cline_hooks.state.skills import record_skill

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture

    from cline_hooks.core.plugin import HookResult
    from tests.conftest import FakeFilesystem


def _pre_shell(command: str, workspace_roots: list[str], agent_id: str | None = None) -> HookResult | None:
    return ShellGuardsPlugin().on_hook(
        PluginScope.PRE_SHELL,
        logger=logging.getLogger("test"),
        command=command,
        task_id=f"t:{agent_id}" if agent_id else "t",
        workspace_roots=workspace_roots,
        agent_id=agent_id,
    )


class TestSkillGuard:
    def test_blocks_read_only_git_in_the_main_session(self) -> None:
        result = _pre_shell("git status", [])
        assert result is not None
        assert result.block is not None
        assert "git-usage" in result.block

    @pytest.mark.parametrize("command", ["git status", "git -P log --oneline", "git diff && git rev-parse HEAD"])
    def test_allows_read_only_git_in_a_subagent(self, command: str) -> None:
        assert _pre_shell(command, [], agent_id="a1") is None

    @pytest.mark.parametrize("command", ["git status && git commit -m x", "git -C /x commit -m x"])
    def test_blocks_other_git_in_a_subagent(self, command: str) -> None:
        result = _pre_shell(command, [], agent_id="a1")
        assert result is not None
        assert result.block is not None
        assert "git-usage" in result.block

    def test_allows_git_commit_in_a_subagent_after_the_skill(self) -> None:
        record_skill("t:a1", "git-usage")
        assert _pre_shell("git commit -m x", [], agent_id="a1") is None


class TestSkillPathInBlock:
    def test_pi_block_names_the_existing_skill_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        skill = tmp_path / "skills" / "git-usage" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("x")
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
        set_protocol(PiProtocol())
        result = _pre_shell("git status", [])
        assert result is not None
        assert result.block == f"MUST use the `git-usage` skill before running this command - read {skill} first"

    def test_pi_block_without_the_skill_file_keeps_the_plain_text(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
        set_protocol(PiProtocol())
        result = _pre_shell("git status", [])
        assert result is not None
        assert result.block == "MUST use the `git-usage` skill before running this command"

    def test_claude_block_names_the_home_skill_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        skill = tmp_path / ".claude" / "skills" / "git-usage" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("x")
        set_protocol(ClaudeCodeProtocol())
        result = _pre_shell("git status", [])
        assert result is not None
        assert result.block is not None
        assert str(skill) in result.block


class TestOversizedSearchGuard:
    def test_blocks_a_search_of_the_home_directory(self, fake_home: Path) -> None:
        result = _pre_shell("rg foo ~", [])
        assert result is not None
        assert result.block is not None
        assert "MUST narrow" in result.block

    def test_allows_a_search_of_a_small_workspace(self, fake_filesystem: FakeFilesystem) -> None:
        repo = fake_filesystem.add_files("/fake/repo", 1)
        assert _pre_shell("rg foo", [repo]) is None

    def test_pathless_search_without_workspace_uses_the_process_directory(
        self, fake_home: Path, mocker: MockerFixture
    ) -> None:
        mocker.patch("os.getcwd", return_value=str(fake_home))
        result = _pre_shell("rg foo", [])
        assert result is not None
        assert result.block is not None


def _herdr_list(*linked_paths: str) -> str:
    workspaces = [
        {"workspace_id": f"w{index}", "worktree": {"checkout_path": path}} for index, path in enumerate(linked_paths)
    ]
    return json.dumps({"result": {"workspaces": workspaces}})


@pytest.fixture
def herdr_output(mocker: MockerFixture) -> MagicMock:
    mocker.patch("cline_hooks.handlers.herdr_guard.shutil.which", return_value="/usr/bin/herdr")
    run = mocker.patch("cline_hooks.handlers.herdr_guard.subprocess.run")
    run.return_value.returncode = 0
    run.return_value.stdout = _herdr_list("/wt/linked")
    return run


class TestHerdrWorktreeGuard:
    def test_blocks_removing_a_worktree_a_workspace_links(self, herdr_output: MagicMock) -> None:
        record_skill("t", "git-usage")
        result = _pre_shell("git worktree remove /wt/linked", ["/repo"])
        assert result is not None
        assert result.block is not None
        assert "w0" in result.block
        assert "herdr workspace close w0" in result.block

    def test_resolves_relative_paths_against_the_workspace_root(self, herdr_output: MagicMock) -> None:
        record_skill("t", "git-usage")
        result = _pre_shell("git worktree remove --force linked", ["/wt"])
        assert result is not None
        assert result.block is not None

    def test_allows_removing_an_unlinked_worktree(self, herdr_output: MagicMock) -> None:
        record_skill("t", "git-usage")
        assert _pre_shell("git worktree remove /wt/other", ["/repo"]) is None

    def test_does_not_query_herdr_for_other_commands(self, herdr_output: MagicMock) -> None:
        record_skill("t", "git-usage")
        assert _pre_shell("git worktree list", ["/repo"]) is None
        herdr_output.assert_not_called()

    def test_fails_open_when_herdr_errors(self, herdr_output: MagicMock) -> None:
        record_skill("t", "git-usage")
        herdr_output.return_value.returncode = 1
        assert _pre_shell("git worktree remove /wt/linked", ["/repo"]) is None

    def test_fails_open_on_unparseable_herdr_output(self, herdr_output: MagicMock) -> None:
        record_skill("t", "git-usage")
        herdr_output.return_value.stdout = "not json"
        assert _pre_shell("git worktree remove /wt/linked", ["/repo"]) is None

    def test_allows_removal_when_herdr_is_not_installed(self, herdr_output: MagicMock, mocker: MockerFixture) -> None:
        record_skill("t", "git-usage")
        mocker.patch("cline_hooks.handlers.herdr_guard.shutil.which", return_value=None)
        assert _pre_shell("git worktree remove /wt/linked", ["/repo"]) is None
        herdr_output.assert_not_called()
