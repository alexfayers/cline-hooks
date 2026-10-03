from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cline_hooks.plugins.handback_rescue import _ORPHANED_NOTE, HandbackRescuePlugin

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.conftest import StubTranscript

    StubTranscriptT = Callable[..., StubTranscript]

_LOGGER = logging.getLogger("test")


def _on_hook(hook_name: str = "PostToolUse", **kwargs: object) -> list[str] | None:
    result = HandbackRescuePlugin().on_hook(hook_name, logger=_LOGGER, **kwargs)
    return None if result is None else result.notes


class TestHandbackRescuePlugin:
    def test_emits_the_rescued_report(self, stub_transcript: StubTranscriptT) -> None:
        stub_transcript(subagent_report_text="the report")
        notes = _on_hook(withheld_report_agent_id="agent-abc", transcript_path="session.jsonl")
        assert notes == ["RESCUED SUBAGENT REPORT (handback withheld by harness, agentId=agent-abc):\nthe report"]

    def test_silent_when_no_report_was_withheld(self, stub_transcript: StubTranscriptT) -> None:
        stub_transcript(subagent_report_text="the report")
        assert _on_hook(withheld_report_agent_id="", transcript_path="session.jsonl") is None

    def test_silent_without_a_transcript_path(self, stub_transcript: StubTranscriptT) -> None:
        stub_transcript(subagent_report_text="the report")
        assert _on_hook(withheld_report_agent_id="agent-abc", transcript_path="") is None

    def test_silent_when_the_transcript_holds_no_report(self, stub_transcript: StubTranscriptT) -> None:
        stub_transcript(subagent_report_text="")
        assert _on_hook(withheld_report_agent_id="agent-abc", transcript_path="session.jsonl") is None

    def test_silent_for_other_hooks(self, stub_transcript: StubTranscriptT) -> None:
        stub_transcript(subagent_report_text="the report")
        assert _on_hook("TaskStart", withheld_report_agent_id="agent-abc", transcript_path="session.jsonl") is None

    def test_tells_an_orphaned_subagent_to_stop_retrying(self) -> None:
        assert _on_hook("ToolFailed", orphaned_handback=True) == [_ORPHANED_NOTE]

    def test_silent_for_a_failed_tool_that_is_not_an_orphaned_handback(self) -> None:
        assert _on_hook("ToolFailed", orphaned_handback=False) is None

    def test_silent_on_post_tool_use_for_an_orphaned_handback(self) -> None:
        assert _on_hook("PostToolUse", orphaned_handback=True) is None
