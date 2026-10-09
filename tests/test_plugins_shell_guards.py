from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.vocabulary import PluginScope
from cline_hooks.plugins.shell_guards import ShellGuardsPlugin
from cline_hooks.state.skills import record_skill

if TYPE_CHECKING:
    from pathlib import Path

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
