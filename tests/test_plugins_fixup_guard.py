from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import git
import pytest

from cline_hooks.core.vocabulary import PluginScope
from cline_hooks.plugins.fixup_guard import FixupGuardPlugin, _repo_state

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture

    from cline_hooks.core.plugin import HookResult

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


UNPUSHED = [["abc1234 add feature", "feature.txt"]]


@pytest.fixture
def repo_state(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("cline_hooks.plugins.fixup_guard._repo_state", return_value=(UNPUSHED, {"feature.txt"}))


def _guard(command: str) -> HookResult | None:
    return FixupGuardPlugin().on_hook(
        PluginScope.PRE_SHELL, logger=logging.getLogger("test"), command=command, workspace_roots=["/work"]
    )


def test_blocks_a_commit_overlapping_an_unpushed_commit_and_names_it(repo_state: MagicMock) -> None:
    result = _guard("git commit -m tweak")
    assert result is not None
    assert "abc1234 add feature (feature.txt)" in str(result.block)
    assert "--fixup=<sha>" in str(result.block)
    assert "# new-feature" in str(result.block)
    repo_state.assert_called_once_with("/work", False)


@pytest.mark.parametrize("command", ["git commit -am tweak", "git add feature.txt && git commit -m tweak"])
def test_includes_unstaged_changes_when_the_command_stages_them(repo_state: MagicMock, command: str) -> None:
    assert _guard(command) is not None
    repo_state.assert_called_once_with("/work", True)


def test_follows_git_dash_c(repo_state: MagicMock) -> None:
    _guard("git -C /other commit -m x")
    repo_state.assert_called_once_with("/other", False)


@pytest.mark.parametrize(
    "command",
    [
        "git commit --fixup=HEAD",
        "git commit --squash HEAD -m x",
        "git commit --amend --no-edit",
        "git commit -m tweak # new-feature",
        "git status",
    ],
)
def test_allows_folds_the_opt_out_and_other_commands(repo_state: MagicMock, command: str) -> None:
    assert _guard(command) is None
    repo_state.assert_not_called()


def test_allows_a_commit_of_files_no_unpushed_commit_touches(repo_state: MagicMock) -> None:
    repo_state.return_value = (UNPUSHED, {"shared.txt"})
    assert _guard("git commit -m follow-up") is None


def test_repo_state_lists_unpushed_commits_and_changed_files(tmp_path: Path) -> None:
    origin = git.Repo.init(tmp_path / "origin.git", bare=True, initial_branch="main")
    repo = git.Repo.init(tmp_path / "work", initial_branch="main")
    for key, value in {"user.name": "Test", "user.email": "test@example.com", "commit.gpgsign": "false"}.items():
        repo.git.config(key, value)
    repo.git.config("core.hooksPath", str(tmp_path / "no-hooks"))
    repo.create_remote("origin", str(origin.working_dir))
    workdir = Path(str(repo.working_tree_dir))
    (workdir / "shared.txt").write_text("a")
    repo.git.add("shared.txt")
    repo.git.commit("-m", "initial")
    repo.git.push("-u", "origin", "main")
    (workdir / "feature.txt").write_text("a")
    repo.git.add("feature.txt")
    repo.git.commit("-m", "add feature")
    (workdir / "feature.txt").write_text("b")
    repo.git.add("feature.txt")
    expected = ([[f"{repo.head.commit.hexsha[:7]} add feature", "feature.txt"]], {"feature.txt"})

    assert _repo_state(str(workdir), include_unstaged=False) == expected
    repo.git.checkout("-b", "topic")
    assert _repo_state(str(workdir), include_unstaged=False) == expected
    (Path(repo.git_dir) / "rebase-merge").mkdir()
    assert _repo_state(str(workdir), include_unstaged=False) == ([], set())
