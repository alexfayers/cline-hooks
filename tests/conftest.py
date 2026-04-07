from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cline_hooks.frontends.cline import ClineProtocol
import cline_hooks.memory_tracker as memory_tracker_module
from cline_hooks.protocol import set_protocol
import cline_hooks.skill_tracker as skill_tracker_module
import cline_hooks.state as state_module

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def isolate_state_files(mocker: MockerFixture, tmp_path: Path) -> None:
    """Redirect all state file paths to tmp_path and set default protocol."""
    mocker.patch.object(state_module, "_STATE_PATH", tmp_path / "hook-state.json")
    mocker.patch.object(skill_tracker_module, "_STATE_PATH", tmp_path / "skill-state.json")
    mocker.patch.object(memory_tracker_module, "_STATE_PATH", tmp_path / "memory-tracker-state.json")
    set_protocol(ClineProtocol())
