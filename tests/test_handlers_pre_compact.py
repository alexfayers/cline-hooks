from __future__ import annotations

from cline_hooks.core.models import HookInputPreCompact, PreCompactFields
from cline_hooks.core.outcome import Disposition
from cline_hooks.handlers.pre_compact import handle_pre_compact


def _pre_compact(*, conversation_length: int = 10, estimated_tokens: int = 100) -> HookInputPreCompact:
    return HookInputPreCompact(
        taskId="task-1",
        workspaceRoots=["/workspace"],
        hookName="PreCompact",
        preCompact=PreCompactFields(conversationLength=conversation_length, estimatedTokens=estimated_tokens),
    )


class TestHandlePreCompact:
    def test_no_pre_compact_fields_allows_with_no_message(self) -> None:
        hook = HookInputPreCompact(taskId="task-1", workspaceRoots=["/workspace"], hookName="PreCompact")
        outcome = handle_pre_compact(hook)
        assert outcome is not None
        assert outcome.disposition is Disposition.ALLOW
        assert outcome.message is None

    def test_reports_conversation_length_and_estimated_tokens(self) -> None:
        outcome = handle_pre_compact(_pre_compact(conversation_length=42, estimated_tokens=12345))
        assert outcome is not None
        assert outcome.message is not None
        assert "42 messages" in outcome.message
        assert "~12345 tokens" in outcome.message

    def test_message_carries_reminder_label(self) -> None:
        outcome = handle_pre_compact(_pre_compact())
        assert outcome is not None
        assert outcome.label == "REMINDER"
