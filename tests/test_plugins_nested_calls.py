from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cline_hooks.core.plugin import HookResult
from cline_hooks.core.vocabulary import CanonicalHook
from cline_hooks.plugins.build_tools import BuildToolsPlugin
from cline_hooks.plugins.delegation import DelegationPlugin
from cline_hooks.plugins.ecosystem import EcosystemPlugin
from cline_hooks.plugins.handback_rescue import HandbackRescuePlugin
from cline_hooks.plugins.nudges import _RETRO_THRESHOLD, NudgesPlugin, _store, mark_edited
from cline_hooks.plugins.persistence import PersistencePlugin
from cline_hooks.state.retrospective import get_count, record_session
from cline_hooks.state.workspace import record_workspace

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from pytest_mock import MockerFixture

    from tests.conftest import StubTranscript


def test_nested_call_gets_no_workspace_note(tmp_path: Path) -> None:
    record_workspace("t", ["/old"])
    (tmp_path / "pyproject.toml").write_text("")
    result = EcosystemPlugin().on_hook(
        CanonicalHook.POST_TOOL_USE,
        logger=logging.getLogger("test"),
        task_id="t",
        workspace_roots=[str(tmp_path)],
        parent_tool_call_id="outer",
    )
    assert result is None


def test_nested_build_failure_keeps_the_alert() -> None:
    result = BuildToolsPlugin().on_hook(
        CanonicalHook.POST_TOOL_USE,
        logger=logging.getLogger("test"),
        tool_result="BUILD FAILED",
        parent_tool_call_id="outer",
    )
    assert isinstance(result, HookResult)


def test_nested_edit_marks_the_session_edited_and_keeps_the_commit_reminder(mocker: MockerFixture) -> None:
    mocker.patch("cline_hooks.plugins.nudges._get_diff_line_count", return_value=500)
    result = NudgesPlugin().on_hook(
        CanonicalHook.POST_TOOL_USE,
        logger=logging.getLogger("test"),
        task_id="t",
        tool_name="replace_in_file",
        parameters={},
        workspace_roots=["/ws"],
        parent_tool_call_id="outer",
    )
    assert isinstance(result, HookResult)
    assert "500 lines changed" in result.notes[0]
    assert _store.get("t").edited


def test_nested_wrap_up_skill_counts_the_session_and_keeps_the_retrospective_reminder() -> None:
    for i in range(_RETRO_THRESHOLD - 1):
        record_session(f"seed-{i}")
    result = NudgesPlugin().on_hook(
        CanonicalHook.POST_TOOL_USE,
        logger=logging.getLogger("test"),
        task_id="t",
        tool_name="use_skill",
        parameters={"skill": "session-end"},
        parent_tool_call_id="outer",
    )
    assert isinstance(result, HookResult)
    assert "/retrospective" in result.notes[0]
    assert get_count() == _RETRO_THRESHOLD


def test_nested_session_end_keeps_the_memory_warning() -> None:
    mark_edited("t")
    result = PersistencePlugin().on_hook(
        CanonicalHook.POST_TOOL_USE,
        logger=logging.getLogger("test"),
        task_id="t",
        tool_name="use_skill",
        parameters={"skill": "session-end"},
        parent_tool_call_id="outer",
    )
    assert isinstance(result, HookResult)
    assert "memory" in result.notes[0]


def test_nested_edit_keeps_the_delegation_nudge(mocker: MockerFixture) -> None:
    mocker.patch.dict("os.environ", {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}, clear=True)
    result = DelegationPlugin().on_hook(
        CanonicalHook.PRE_TOOL_USE,
        logger=logging.getLogger("test"),
        task_id="t",
        tool_name="replace_in_file",
        parameters={},
        workspace_roots=[],
        parent_tool_call_id="outer",
    )
    assert isinstance(result, HookResult)
    assert "delegat" in result.notes[0].lower()


def test_nested_call_keeps_the_rescued_report(stub_transcript: Callable[..., StubTranscript]) -> None:
    stub_transcript(subagent_report_text="the report")
    result = HandbackRescuePlugin().on_hook(
        CanonicalHook.POST_TOOL_USE,
        logger=logging.getLogger("test"),
        withheld_report_agent_id="agent-abc",
        transcript_path="session.jsonl",
        parent_tool_call_id="outer",
    )
    assert isinstance(result, HookResult)
    assert "the report" in result.notes[0]
