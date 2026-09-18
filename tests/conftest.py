from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.frontends import DEFAULT_PROTOCOL
from cline_hooks.core.protocol import get_protocol, set_protocol
from cline_hooks.core.transcript import TranscriptReader
import cline_hooks.plugins.context_usage as context_usage_module
import cline_hooks.plugins.delegation as delegation_module
import cline_hooks.plugins.nudges as nudges_module
import cline_hooks.plugins.plan_handoff as plan_handoff_module
import cline_hooks.plugins.research as research_module
import cline_hooks.state.agents as agents_tracker_module
import cline_hooks.state.memory as memory_tracker_module
import cline_hooks.state.retrospective as retrospective_module
import cline_hooks.state.skills as skill_tracker_module
import cline_hooks.state.store as state_store_module
import cline_hooks.state.workspace as workspace_module

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from pytest_mock import MockerFixture


@dataclass
class StubTranscript(TranscriptReader):
    """A scriptable transcript reader that answers empty without a path."""

    tokens: int | None = None
    text: str = ""

    def context_tokens(self, transcript_path: str) -> int | None:
        """Return the scripted token count.

        Returns:
            The scripted count when a transcript is named, otherwise None.
        """
        return self.tokens if transcript_path else None

    def turn_assistant_text(self, transcript_path: str) -> str:
        """Return the scripted assistant text.

        Returns:
            The scripted text when a transcript is named, otherwise "".
        """
        return self.text if transcript_path else ""


@pytest.fixture
def stub_transcript(
    mocker: MockerFixture,
) -> Callable[..., StubTranscript]:
    """Swap the active protocol's transcript reader for a scripted stub.

    Returns:
        A callable taking `tokens` and/or `text` that installs the stub.
    """

    def install(*, tokens: int | None = None, text: str = "") -> StubTranscript:
        stub = StubTranscript(tokens=tokens, text=text)
        mocker.patch.object(type(get_protocol()), "transcript", stub)
        return stub

    return install


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
    mocker.patch.object(nudges_module._store, "_path", tmp_path / "turns-state.json")
    mocker.patch.object(agents_tracker_module, "_STATE_PATH", tmp_path / "agents-state.json")
    mocker.patch.object(context_usage_module._store, "_path", tmp_path / "context-state.json")
    mocker.patch.object(plan_handoff_module._store, "_path", tmp_path / "plan-state.json")
    mocker.patch.object(research_module._store, "_path", tmp_path / "research-state.json")
    mocker.patch.object(workspace_module, "_STATE_PATH", tmp_path / "workspace-state.json")
    mocker.patch.object(delegation_module._store, "_path", tmp_path / "delegation-state.json")
    mocker.patch.dict(os.environ, {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": ""})
    set_protocol(DEFAULT_PROTOCOL())
