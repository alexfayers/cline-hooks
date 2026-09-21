from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

import cline_hooks.plugins.managed_files as managed_files_module
from cline_hooks.plugins.managed_files import _get_managed_files

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def _reset_cache(mocker: MockerFixture) -> None:
    mocker.patch.object(managed_files_module, "_managed_files", None)
    mocker.patch.object(managed_files_module, "_managed_files_mtime", None)


@pytest.fixture
def manifest(tmp_path: Path, mocker: MockerFixture) -> Path:
    path = tmp_path / "installed.json"
    mocker.patch.object(managed_files_module, "_MANIFEST_PATH", path)
    return path


class TestGetManagedFiles:
    def test_re_reads_after_the_manifest_is_modified(self, manifest: Path, mocker: MockerFixture) -> None:
        manifest.write_text("{}", encoding="utf-8")
        mocker.patch.object(managed_files_module, "_get_managed_files_impl", side_effect=[{"/a"}, {"/a", "/b"}])
        assert _get_managed_files() == {"/a"}
        bumped_mtime = manifest.stat().st_mtime + 1
        os.utime(manifest, (bumped_mtime, bumped_mtime))
        assert _get_managed_files() == {"/a", "/b"}

    def test_re_reads_once_the_manifest_starts_existing(self, manifest: Path, mocker: MockerFixture) -> None:
        mocker.patch.object(managed_files_module, "_get_managed_files_impl", side_effect=[set(), {"/a"}])
        assert _get_managed_files() == set()
        manifest.write_text("{}", encoding="utf-8")
        assert _get_managed_files() == {"/a"}

    def test_a_failed_read_is_retried_on_the_next_call(self, manifest: Path, mocker: MockerFixture) -> None:
        manifest.write_text("{}", encoding="utf-8")
        mocker.patch.object(
            managed_files_module, "_get_managed_files_impl", side_effect=[RuntimeError("transient"), {"/a"}]
        )
        with pytest.raises(RuntimeError):
            _get_managed_files()
        assert _get_managed_files() == {"/a"}

    def test_returns_empty_set_when_llm_prompts_is_unavailable(self, mocker: MockerFixture) -> None:
        mocker.patch.object(managed_files_module, "_MANIFEST_PATH", None)
        mocker.patch.object(managed_files_module, "_get_managed_files_impl", None)
        assert _get_managed_files() == set()
