from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.protocol import set_protocol
from cline_hooks.frontends.cline import ClineProtocol
import cline_hooks.state.agents as agents_tracker_module
import cline_hooks.state.context as context_module
import cline_hooks.state.memory as memory_tracker_module
import cline_hooks.state.plan as plan_module
import cline_hooks.state.research as research_tracker_module
import cline_hooks.state.retrospective as retrospective_module
import cline_hooks.state.skills as skill_tracker_module
import cline_hooks.state.store as state_store_module
import cline_hooks.state.turns as turns_module
import cline_hooks.state.workspace as workspace_module

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.fixture(autouse=True, scope="session")
def isolate_log_file(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Redirect the "hooks" logger away from the real, shared log file.

    cline_hooks._main configures logging.basicConfig at import time against the
    real user log file; without this, running the test suite writes deliberate
    test-triggered tracebacks into the same log live hook invocations use.
    """
    log_path = tmp_path_factory.mktemp("logs") / "cline-hooks.log"
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.addHandler(logging.FileHandler(log_path))


@pytest.fixture(autouse=True)
def isolate_state_files(mocker: MockerFixture, tmp_path: Path) -> None:
    """Redirect all state file paths to tmp_path and set default protocol."""
    mocker.patch.object(state_store_module, "_STATE_PATH", tmp_path / "hook-state.json")
    mocker.patch.object(skill_tracker_module, "_STATE_PATH", tmp_path / "skill-state.json")
    mocker.patch.object(memory_tracker_module, "_STATE_PATH", tmp_path / "memory-state.json")
    mocker.patch.object(retrospective_module, "_STATE_PATH", tmp_path / "retrospective-state.json")
    mocker.patch.object(turns_module, "_STATE_PATH", tmp_path / "turns-state.json")
    mocker.patch.object(agents_tracker_module, "_STATE_PATH", tmp_path / "agents-state.json")
    mocker.patch.object(context_module, "_STATE_PATH", tmp_path / "context-state.json")
    mocker.patch.object(plan_module, "_STATE_PATH", tmp_path / "plan-state.json")
    mocker.patch.object(research_tracker_module, "_STATE_PATH", tmp_path / "research-state.json")
    mocker.patch.object(workspace_module, "_STATE_PATH", tmp_path / "workspace-state.json")
    set_protocol(ClineProtocol())
