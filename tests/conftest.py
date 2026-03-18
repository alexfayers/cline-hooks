from __future__ import annotations

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

import cline_hooks.memory_tracker as memory_tracker_module
import cline_hooks.skill_tracker as skill_tracker_module
import cline_hooks.state as state_module


@pytest.fixture(autouse=True)
def isolate_state_files(mocker: MockerFixture, tmp_path: Path) -> None:
    """Redirect all state file paths to tmp_path to prevent test pollution."""
    mocker.patch.object(state_module, "_STATE_PATH", tmp_path / "hook-state.json")
    mocker.patch.object(
        skill_tracker_module, "_STATE_PATH", tmp_path / "skill-state.json"
    )
    mocker.patch.object(
        memory_tracker_module, "_STATE_PATH", tmp_path / "memory-tracker-state.json"
    )
