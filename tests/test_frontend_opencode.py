from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn
from unittest.mock import patch

import pytest

from cline_hooks.core.protocol import RawPayload
from cline_hooks.frontends.opencode import OpencodeInstaller, OpencodeProtocol
from cline_hooks.frontends.opencode.models import OpencodeEditParams

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

    def test_skills_live_under_the_opencode_config(self, tmp_path: Path) -> None:
        spec = OpencodeProtocol.frontend_spec
        assert spec is not None
        assert spec.skills_dir is not None
        with patch.object(Path, "home", return_value=tmp_path):
            assert spec.skills_dir() == tmp_path / ".config" / "opencode" / "skills"


class TestOpencodeEditParams:
    def test_edit_without_a_replacement_has_no_diff(self) -> None:
        params = OpencodeEditParams.model_validate({"filePath": "/a.py"})
        assert params.model_dump(exclude_none=True) == {"path": "/a.py"}


class TestOpencodeInstaller:
    def test_install_refuses_until_the_plugin_exists(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert _exit(lambda: OpencodeInstaller().install(OpencodeProtocol, None)) == 1
        assert "cannot be installed yet" in capsys.readouterr().err
