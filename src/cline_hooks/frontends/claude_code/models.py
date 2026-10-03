"""Claude Code's payload models: where its raw hook JSON differs from canonical."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from cline_hooks.core.models import (
    PostToolUseFields,
    StopFields,
    TaskStartFields,
    UserPromptSubmitFields,
)
from cline_hooks.core.payload import Flag, ToolParams, diff_envelope

WITHHELD_REPORT_MARKER = "without delivering a report through SubagentHandback"
ORPHANED_HANDBACK_MARKER = "the agent that spawned you is no longer running"


def _withheld_report_agent_id(data: dict[str, Any]) -> dict[str, Any]:
    """Set `withheldReportAgentId` where an Agent result says its report was withheld.

    Returns:
        The payload, with `withheldReportAgentId` added for a withheld report.
    """
    response = data.get("tool_response")
    if not isinstance(response, dict):
        return data
    agent_id = response.get("agentId")
    content = response.get("content")
    if not isinstance(agent_id, str) or not agent_id or not isinstance(content, list):
        return data
    if any(
        isinstance(block, dict) and isinstance(block.get("text"), str) and WITHHELD_REPORT_MARKER in block["text"]
        for block in content
    ):
        return {**data, "withheldReportAgentId": agent_id}
    return data


def _orphaned_handback(data: dict[str, Any]) -> dict[str, Any]:
    """Set `orphanedHandback` where a SubagentHandback failed because its spawner has ended.

    Returns:
        The payload, with `orphanedHandback` added for an orphaned handback.
    """
    response = data.get("tool_response")
    if (
        data.get("tool_name") == "SubagentHandback"
        and isinstance(response, dict)
        and ORPHANED_HANDBACK_MARKER in str(response.get("message", ""))
    ):
        return {**data, "orphanedHandback": True}
    return data


class ClaudeCodePostToolUse(PostToolUseFields):
    """Claude Code's PostToolUse fields.

    `executionTimeMs` comes from `duration_ms`; `withheldReportAgentId` is set
    from an Agent result reporting its handback was withheld; `orphanedHandback`
    from a SubagentHandback failing because its spawner has ended.
    """

    executionTimeMs: int = Field(default=0, validation_alias="duration_ms")
    withheldReportAgentId: str = ""
    orphanedHandback: bool = False

    _withheld = model_validator(mode="before")(_withheld_report_agent_id)
    _orphaned = model_validator(mode="before")(_orphaned_handback)

    def frontend_kwargs(self) -> dict[str, object]:
        """Extra plugin dispatch kwargs a frontend derives from its own payload.

        Returns:
            The withheld-report agent id and orphaned-handback flag.
        """
        return {
            "withheld_report_agent_id": self.withheldReportAgentId,
            "orphaned_handback": self.orphanedHandback,
        }


class ClaudeCodeTaskStart(TaskStartFields):
    """Claude Code's TaskStart fields; `source` maps directly from the payload."""

    source: str = ""


class ClaudeCodeUserPromptSubmit(UserPromptSubmitFields):
    """Claude Code's UserPromptSubmit fields; `userMessage` comes from `prompt`."""

    userMessage: str = Field(default="", validation_alias="prompt")


class ClaudeCodeStop(StopFields):
    """Claude Code's Stop fields; `stopHookActive` comes from `stop_hook_active`."""

    stopHookActive: Flag = Field(default=False, validation_alias="stop_hook_active")


class ClaudeCodeReadParams(ToolParams):
    """Parameters for a Claude Code file read tool call.

    `path` is deliberately not optional - Claude Code always emits it, even
    when `file_path` is absent, unlike Kiro.
    """

    path: str = Field(default="", validation_alias="file_path")


class ClaudeCodeEditWriteParams(ToolParams):
    """Parameters for a Claude Code file edit or write tool call."""

    path: str | None = Field(default=None, validation_alias="file_path")
    diff: str | None = None

    _diff = model_validator(mode="before")(diff_envelope("new_string", "content"))


class ClaudeCodeShellParams(ToolParams):
    """Parameters for a Claude Code shell command execution tool call."""

    command: str = ""
