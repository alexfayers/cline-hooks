from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn
from unittest.mock import patch

import pytest

from cline_hooks.core.protocol import RawPayload
from cline_hooks.frontends.opencode import OpencodeProtocol
from cline_hooks.frontends.opencode.install import config_dir
from cline_hooks.frontends.opencode.models import OpencodeEditParams, patch_file

if TYPE_CHECKING:
    from collections.abc import Callable


def _exit(respond: Callable[[], NoReturn]) -> int | str | None:
    """Run one of a protocol's output methods and return its exit code.

    Returns:
        The code it exited with.
    """
    with pytest.raises(SystemExit) as excinfo:
        respond()
    return excinfo.value.code


class TestOpencodeOutput:
    def test_allow_prints_context_and_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert _exit(lambda: OpencodeProtocol().allow("ctx", system_message="ignored")) == 0
        assert capsys.readouterr().out == "ctx"

    def test_allow_with_input_prints_the_update_as_json(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert _exit(lambda: OpencodeProtocol().allow_with_input({"command": "ls -a"}, "note")) == 0
        assert json.loads(capsys.readouterr().out) == {"updated_input": {"command": "ls -a"}, "message": "note"}

    def test_block_prints_to_stderr_and_exits_two(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert _exit(lambda: OpencodeProtocol().block("nope")) == 2
        assert capsys.readouterr().err == "nope"


class TestOpencodeDetection:
    def test_non_json_payload_is_not_opencode(self) -> None:
        assert OpencodeProtocol.detect(RawPayload(raw="not json", data=None, env={})) is False

    def test_skills_live_under_the_opencode_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENCODE_CONFIG_DIR", raising=False)
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        spec = OpencodeProtocol.frontend_spec
        assert spec is not None
        assert spec.skills_dir is not None
        with patch.object(Path, "home", return_value=tmp_path):
            assert spec.skills_dir() == tmp_path / ".config" / "opencode" / "skills"


class TestOpencodeConfigDir:
    @pytest.mark.parametrize(
        ("env", "expected"),
        [
            ({"OPENCODE_CONFIG_DIR": "oc", "XDG_CONFIG_HOME": "xdg"}, "oc"),
            ({"XDG_CONFIG_HOME": "xdg"}, "xdg/opencode"),
        ],
        ids=["opencode-config-dir", "xdg-config-home"],
    )
    def test_follows_opencodes_lookup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env: dict[str, str], expected: str
    ) -> None:
        monkeypatch.delenv("OPENCODE_CONFIG_DIR", raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, str(tmp_path / value))
        assert config_dir() == tmp_path / expected


class TestOpencodeEditParams:
    def test_edit_without_a_replacement_has_no_diff(self) -> None:
        params = OpencodeEditParams.model_validate({"path": "/a.py"})
        assert params.model_dump(exclude_none=True) == {"path": "/a.py"}


class TestPatchFile:
    def test_added_file_is_all_replace(self) -> None:
        assert patch_file("*** Begin Patch\n*** Add File: d.txt\n+delta\n*** End Patch") == (
            "d.txt",
            "------- SEARCH\n=======\ndelta\n+++++++ REPLACE",
        )

    def test_each_hunk_is_its_own_block(self) -> None:
        text = "*** Begin Patch\n*** Update File: c.txt\n@@\n-a\n+b\n@@ def f():\n-c\n+d\n*** End Patch"
        assert patch_file(text) == (
            "c.txt",
            "------- SEARCH\na\n=======\nb\n+++++++ REPLACE\n------- SEARCH\nc\n=======\nd\n+++++++ REPLACE",
        )

    def test_only_the_first_file_is_read(self) -> None:
        text = "*** Begin Patch\n*** Update File: c.txt\n@@\n-a\n+b\n*** Add File: d.txt\n+delta\n*** End Patch"
        parsed = patch_file(text)
        assert parsed is not None
        assert parsed[0] == "c.txt"
        assert "delta" not in (parsed[1] or "")

    def test_deleted_file_has_no_diff(self) -> None:
        assert patch_file("*** Begin Patch\n*** Delete File: old.txt\n*** End Patch") == ("old.txt", None)

    def test_text_without_a_file_is_none(self) -> None:
        assert patch_file("not a patch") is None
