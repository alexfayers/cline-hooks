from __future__ import annotations

from typing import TYPE_CHECKING

import git

from cline_hooks.handlers.push_guard import marker_above_repo

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


class TestMarkerAboveRepo:
    def test_returns_none_when_no_markers_configured(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch("cline_hooks.handlers.push_guard.get_push_block_markers", return_value=())
        git.Repo.init(tmp_path)
        assert marker_above_repo([str(tmp_path)]) is None

    def test_returns_none_when_no_repo_found(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch("cline_hooks.handlers.push_guard.get_push_block_markers", return_value=("some-marker",))
        assert marker_above_repo([str(tmp_path)]) is None

    def test_finds_marker_at_repo_root(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch("cline_hooks.handlers.push_guard.get_push_block_markers", return_value=("some-marker",))
        git.Repo.init(tmp_path)
        (tmp_path / "some-marker").mkdir()
        assert marker_above_repo([str(tmp_path)]) == "some-marker"

    def test_finds_marker_above_repo_root(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch("cline_hooks.handlers.push_guard.get_push_block_markers", return_value=("some-marker",))
        (tmp_path / "some-marker").mkdir()
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        git.Repo.init(repo_dir)
        assert marker_above_repo([str(repo_dir)]) == "some-marker"

    def test_returns_none_when_marker_not_found(self, tmp_path: Path, mocker: MockerFixture) -> None:
        mocker.patch("cline_hooks.handlers.push_guard.get_push_block_markers", return_value=("some-marker",))
        git.Repo.init(tmp_path)
        assert marker_above_repo([str(tmp_path)]) is None
