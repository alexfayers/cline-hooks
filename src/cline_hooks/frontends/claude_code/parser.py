"""Claude Code's tool-name table and registered pydantic payload models."""

from __future__ import annotations

from pydantic import Field, model_validator

from cline_hooks.core.models import StopFields, TaskStartFields, UserPromptSubmitFields
from cline_hooks.core.payload import Flag, ToolParams, diff_envelope, payload_model
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool, Frontend

_TOOL_MAP: dict[str, CanonicalTool] = {
    "Bash": CanonicalTool.SHELL,
    "Read": CanonicalTool.READ,
    "Edit": CanonicalTool.EDIT,
    "Write": CanonicalTool.WRITE,
    "Skill": CanonicalTool.SKILL,
    "Task": CanonicalTool.SPAWN_AGENT,
    "Agent": CanonicalTool.SPAWN_AGENT,
    "Workflow": CanonicalTool.SPAWN_AGENT,
    "ExitPlanMode": CanonicalTool.PLAN_EXIT,
    "WebFetch": CanonicalTool.WEB_FETCH,
    "WebSearch": CanonicalTool.WEB_SEARCH,
}


@payload_model(Frontend.CLAUDE_CODE, CanonicalHook.TASK_START)
class ClaudeCodeTaskStart(TaskStartFields):
    """Claude Code's TaskStart fields; `source` maps directly from the payload."""

    source: str = ""


@payload_model(Frontend.CLAUDE_CODE, CanonicalHook.USER_PROMPT_SUBMIT)
class ClaudeCodeUserPromptSubmit(UserPromptSubmitFields):
    """Claude Code's UserPromptSubmit fields; `userMessage` comes from `prompt`."""

    userMessage: str = Field(default="", validation_alias="prompt")


@payload_model(Frontend.CLAUDE_CODE, CanonicalHook.STOP)
class ClaudeCodeStop(StopFields):
    """Claude Code's Stop fields; `stopHookActive` comes from `stop_hook_active`."""

    stopHookActive: Flag = Field(default=False, validation_alias="stop_hook_active")


@payload_model(Frontend.CLAUDE_CODE, CanonicalTool.READ)
class ClaudeCodeReadParams(ToolParams):
    """Parameters for a Claude Code file read tool call.

    `path` is deliberately not optional - Claude Code always emits it, even
    when `file_path` is absent, unlike Kiro.
    """

    path: str = Field(default="", validation_alias="file_path")


@payload_model(Frontend.CLAUDE_CODE, CanonicalTool.EDIT, CanonicalTool.WRITE)
class ClaudeCodeEditWriteParams(ToolParams):
    """Parameters for a Claude Code file edit or write tool call."""

    path: str | None = Field(default=None, validation_alias="file_path")
    diff: str | None = None

    _diff = model_validator(mode="before")(diff_envelope("new_string", "content"))


@payload_model(Frontend.CLAUDE_CODE, CanonicalTool.SHELL)
class ClaudeCodeShellParams(ToolParams):
    """Parameters for a Claude Code shell command execution tool call."""

    command: str = ""
