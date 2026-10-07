from __future__ import annotations

import importlib.metadata
import os
import sys
from typing import TYPE_CHECKING

import pytest

import cline_hooks.daemon.fingerprint as fingerprint_module
from cline_hooks.daemon.fingerprint import cached, compute

if TYPE_CHECKING:
    from pathlib import Path
    from unittest.mock import Mock

    from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def isolate_cache(mocker: MockerFixture) -> None:
    mocker.patch.object(fingerprint_module, "_cache", None)


@pytest.fixture(autouse=True)
def skip_real_source_tree(mocker: MockerFixture) -> None:
    source_files = fingerprint_module._source_files
    mocker.patch.object(
        fingerprint_module,
        "_source_files",
        side_effect=lambda top_level: [] if top_level == "cline_hooks" else source_files(top_level),
    )


@pytest.fixture
def entry_point(mocker: MockerFixture) -> Mock:
    """Expose one fake plugin entry point.

    Returns:
        The entry point, whose `module` and `dist.version` tests may change.
    """
    entry_point: Mock = mocker.Mock()
    entry_point.dist.name = "fake-overlay-dist"
    entry_point.dist.version = "1.0.0"
    entry_point.module = "no_such_overlay_pkg"
    mocker.patch.object(importlib.metadata, "entry_points", return_value=[entry_point])
    return entry_point


class TestCompute:
    def test_changes_when_a_distribution_version_changes(self, entry_point: Mock) -> None:
        before = compute()
        entry_point.dist.version = "2.0.0"
        assert compute() != before

    @pytest.mark.parametrize(
        ("files", "module", "touched", "changes"),
        [
            (
                ("fake_overlay_pkg/__init__.py", "fake_overlay_pkg/plugin.py"),
                "fake_overlay_pkg.plugin",
                "fake_overlay_pkg/plugin.py",
                True,
            ),
            (("fake_overlay_mod.py",), "fake_overlay_mod", "fake_overlay_mod.py", True),
            (
                ("fake_overlay_pkg/__init__.py", "fake_overlay_pkg/__pycache__/x.pyc"),
                "fake_overlay_pkg",
                "fake_overlay_pkg/__pycache__/x.pyc",
                False,
            ),
        ],
        ids=["package-source", "single-module", "bytecode"],
    )
    def test_tracks_entry_point_source_files_without_importing_them(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]
        self,
        entry_point: Mock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        files: tuple[str, ...],
        module: str,
        touched: str,
        changes: bool,
    ) -> None:
        for name in files:
            (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / name).write_text("")
        monkeypatch.syspath_prepend(tmp_path)
        entry_point.module = module
        before = compute()

        path = tmp_path / touched
        os.utime(path, (path.stat().st_atime, path.stat().st_mtime + 100))

        assert (compute() != before) is changes
        assert module.split(".", maxsplit=1)[0] not in sys.modules

    def test_tolerates_an_entry_point_whose_module_is_missing(self, entry_point: Mock) -> None:
        assert compute()


class TestCached:
    def test_matches_a_fresh_compute(self) -> None:
        assert cached() == compute()
