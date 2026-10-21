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
    entry_point: Mock = mocker.Mock()
    entry_point.dist.name = "fake-overlay-dist"
    entry_point.dist.version = "1.0.0"
    entry_point.module = "no_such_overlay_pkg"
    mocker.patch.object(importlib.metadata, "entry_points", return_value=[entry_point])
    return entry_point


def test_compute_changes_when_a_distribution_version_changes(entry_point: Mock) -> None:
    before = compute()
    entry_point.dist.version = "2.0.0"
    assert compute() != before


@pytest.mark.parametrize(
    ("files", "module", "touched", "changes"),
    [
        (("pkg/__init__.py", "pkg/plugin.py"), "pkg.plugin", "pkg/plugin.py", True),
        (("single_mod.py",), "single_mod", "single_mod.py", True),
        (("pkg/__init__.py", "pkg/__pycache__/x.pyc"), "pkg", "pkg/__pycache__/x.pyc", False),
    ],
    ids=["package-source", "single-module", "bytecode"],
)
def test_compute_tracks_entry_point_source_files_without_importing_them(  # ruff: ignore[too-many-arguments, too-many-positional-arguments]
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


def test_cached_matches_a_fresh_compute() -> None:
    assert cached() == compute()
