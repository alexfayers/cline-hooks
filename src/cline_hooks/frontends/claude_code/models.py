"""Claude Code's payload models: where its raw hook JSON differs from canonical."""

from __future__ import annotations

from pydantic import Field, model_validator

from cline_hooks.core.models import (
    PostToolUseFields,
    StopFields,
    TaskStartFields,
    UserPromptSubmitFields,
)
from cline_hooks.core.payload import Flag, ToolParams, diff_envelope


class ClaudeCodePostToolUse(PostToolUseFields):
    """Claude Code's PostToolUse fields; `executionTimeMs` comes from `duration_ms`."""

    executionTimeMs: int = Field(default=0, validation_alias="duration_ms")


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
