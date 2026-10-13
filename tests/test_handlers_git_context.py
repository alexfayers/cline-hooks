from __future__ import annotations

from typing import TYPE_CHECKING

import git
import pytest

from cline_hooks.handlers.git_context import MAX_UNMERGED_BRANCHES, get_git_context

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def repo(tmp_path: Path) -> git.Repo:
    created = git.Repo.init(tmp_path, initial_branch="main")
    with created.config_writer() as config:
        config.set_value("user", "name", "Test")
        config.set_value("user", "email", "test@example.com")
    created.git.commit("--allow-empty", "-m", "initial")
    return created


def unmerged_branch(repo: git.Repo, name: str) -> None:
    repo.git.checkout("-b", name)
    repo.git.commit("--allow-empty", "-m", name)
    repo.git.checkout("main")


def context(path: Path) -> str:
    return get_git_context([str(path)]) or ""


class TestGitContext:
    def test_an_unmerged_branch_is_listed(self, repo: git.Repo, tmp_path: Path) -> None:
        assert "Unmerged" not in context(tmp_path)

        unmerged_branch(repo, "feat/x")

        assert "Unmerged local branches: feat/x" in context(tmp_path)

    def test_a_long_branch_list_is_capped_with_a_count_of_the_rest(self, repo: git.Repo, tmp_path: Path) -> None:
        names = [f"feat/{index}" for index in range(MAX_UNMERGED_BRANCHES + 1)]
        for name in names:
            unmerged_branch(repo, name)

        shown = ", ".join([*names[:MAX_UNMERGED_BRANCHES], "+1 more"])
        assert f"Unmerged local branches: {shown}" in context(tmp_path).splitlines()

    def test_handoff_and_rules_files_are_noted_only_where_present(self, tmp_path: Path, repo: git.Repo) -> None:
        assert "HANDOFF.md" not in context(tmp_path)
        assert "RULES.md" not in context(tmp_path)

        (tmp_path / "HANDOFF.md").write_text("handoff")
        (tmp_path / "RULES.md").write_text("rules")

        assert "HANDOFF.md present: run pickup" in context(tmp_path)
        assert "RULES.md present" in context(tmp_path)

    def test_a_repo_without_commits_still_gives_a_summary(self, tmp_path: Path) -> None:
        git.Repo.init(tmp_path, initial_branch="main")

        assert "Branch: main" in context(tmp_path)

    def test_a_directory_that_is_not_a_repo_gives_no_summary(self, tmp_path: Path) -> None:
        assert get_git_context([str(tmp_path), str(tmp_path / "missing")]) is None
