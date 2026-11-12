from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from cline_hooks._main import _run_hook
from cline_hooks.core.plugin import load_plugins, plugins_override
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool
from cline_hooks.plugins.file_structure import FileStructurePlugin

if TYPE_CHECKING:
    from cline_hooks.core.plugin import HookResult

FIXTURES = Path(__file__).parent / "fixtures" / "PreToolUse" / "tools"


def _create(path: Path, tool: CanonicalTool = CanonicalTool.WRITE, roots: list[str] | None = None) -> HookResult | None:
    return FileStructurePlugin().on_hook(
        CanonicalHook.PRE_TOOL_USE,
        logger=logging.getLogger("test"),
        tool_name=tool,
        parameters={"path": str(path)},
        workspace_roots=roots or [],
    )


def _fill(folder: Path, files: int, subfolders: int = 0) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(files):
        (folder / f"file{index}.txt").write_text("x")
    for index in range(subfolders):
        (folder / f"area{index}").mkdir()
    return folder


def test_notes_a_new_file_that_brings_a_folder_to_eight_files(tmp_path: Path) -> None:
    folder = _fill(tmp_path / "pkg", files=7, subfolders=3)

    result = _create(folder / "new.txt")

    assert result is not None
    assert result.block is None
    assert "short-named area subfolder" in result.notes[0]


@pytest.mark.parametrize(("files", "is_repo_root"), [(6, False), (8, False), (7, True)])
def test_stays_silent_unless_the_new_file_makes_exactly_eight(tmp_path: Path, files: int, is_repo_root: bool) -> None:
    folder = _fill(tmp_path / "pkg", files=files)
    if is_repo_root:
        (folder / ".git").mkdir()

    assert _create(folder / "new.txt") is None


def test_resolves_a_relative_path_against_the_workspace_root(tmp_path: Path) -> None:
    _fill(tmp_path / "pkg", files=7)

    assert _create(Path("pkg/new.txt"), roots=[str(tmp_path)]) is not None


def test_notes_a_new_file_from_a_frontend_payload(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = _fill(tmp_path / "pkg", files=7)
    fixture = (FIXTURES / "pi_Write.json").read_text().replace("/home/user/project/src/app.py", str(folder / "new.txt"))

    with (
        plugins_override([FileStructurePlugin()]),
        patch("builtins.input", return_value=fixture),
        pytest.raises(SystemExit),
    ):
        _run_hook()

    output = capsys.readouterr()
    assert "short-named area subfolder" in output.err + output.out


def test_is_loaded_as_a_bundled_plugin() -> None:
    assert any(isinstance(plugin, FileStructurePlugin) for plugin in load_plugins())
