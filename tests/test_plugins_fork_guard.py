from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool, PluginScope
from cline_hooks.plugins.fork_guard import ForkGuardPlugin
from cline_hooks.plugins.tool_guards import ToolGuardsPlugin

if TYPE_CHECKING:
    from pathlib import Path

    from cline_hooks.core.plugin import HookResult

LEAD: dict[str, object] = {}
FORK: dict[str, object] = {"agent_id": "x"}


def _run_command(command: str, agent: dict[str, object]) -> HookResult | None:
    kwargs = {"tool_name": CanonicalTool.SHELL, "command": command, **agent}
    return ForkGuardPlugin().on_hook(PluginScope.PRE_SHELL, logger=logging.getLogger(), **kwargs)


@pytest.mark.parametrize(
    "command",
    [
        "pytest tests/test_a.py",
        "PYTEST_XDIST_AUTO_NUM_WORKERS=4 just test",
        "uv run pytest -x",
        "python -m pytest",
        "cd app && cargo test --lib",
        "pnpm test",
        "npm run test",
        "pnpm run test -- --watch",
        "uv run --locked pytest",
        "just",
        "cd app && just",
    ],
)
def test_the_lead_is_pointed_to_a_fork_for_a_test_run(command: str) -> None:
    result = _run_command(command, LEAD)
    assert result is not None
    assert result.block is None
    assert any("fork" in note for note in result.notes)


@pytest.mark.parametrize("command", ["pytest tests", "just test"])
def test_a_fork_runs_tests_itself(command: str) -> None:
    assert _run_command(command, FORK) is None


@pytest.mark.parametrize(
    "command",
    ["ls", "git status", "echo pytest", "just build", "just --list", "npm run build", "grep test src", "uv sync"],
)
def test_the_lead_runs_other_commands(command: str) -> None:
    assert _run_command(command, LEAD) is None


@pytest.mark.parametrize("command", ["gdb ./app", "python -m pdb script.py", "uv run ipdb x.py", "dlv debug ."])
def test_the_lead_is_pointed_to_a_fork_for_debugging(command: str) -> None:
    result = _run_command(command, LEAD)
    assert result is not None
    assert result.block is None
    assert "debugging" in result.notes[0]
    assert _run_command(command, FORK) is None


@pytest.mark.parametrize(("agent", "points_to_fork"), [(LEAD, True), (FORK, False)])
def test_only_the_lead_is_sent_to_a_fork_for_a_read_of_a_long_file(
    tmp_path: Path, agent: dict[str, object], points_to_fork: bool
) -> None:
    path = tmp_path / "long.txt"
    path.write_text("\n" * 1001)
    kwargs = {"tool_name": CanonicalTool.READ, "parameters": {"path": str(path)}, **agent}
    result = ToolGuardsPlugin().on_hook(CanonicalHook.PRE_TOOL_USE, logger=logging.getLogger(), **kwargs)
    assert result is not None
    assert result.block is not None
    assert ("fork" in result.block) is points_to_fork
