"""Kiro's tool-name table and registered pydantic payload models."""

from __future__ import annotations

from typing import ClassVar

from pydantic import AliasPath, Field, model_validator

from cline_hooks.core.models import StopFields, TaskStartFields, UserPromptSubmitFields
from cline_hooks.core.payload import (
    Flag,
    PayloadEnvelope,
    ToolParams,
    diff_envelope,
    payload_model,
)
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool, Frontend

_KIRO_TOOL_MAP: dict[str, CanonicalTool] = {
    "shell": CanonicalTool.SHELL,
    "execute_bash": CanonicalTool.SHELL,
    "read": CanonicalTool.READ,
    "fs_read": CanonicalTool.READ,
    "write": CanonicalTool.EDIT,
    "fs_write": CanonicalTool.EDIT,
    "grep": CanonicalTool.READ,
    "use_aws": CanonicalTool.SHELL,
    "call_aws": CanonicalTool.SHELL,
}


@payload_model(Frontend.KIRO)
class KiroEnvelope(PayloadEnvelope):
    """Kiro's envelope, using the same raw keys as Claude Code's."""

    session_env_keys: ClassVar[tuple[str, ...]] = ("KIRO_SESSION_ID",)


@payload_model(Frontend.KIRO, CanonicalHook.TASK_START)
class KiroTaskStartFields(TaskStartFields):
    """Kiro's TaskStart fields."""

    source: str = ""


@payload_model(Frontend.KIRO, CanonicalHook.USER_PROMPT_SUBMIT)
class KiroUserPromptSubmitFields(UserPromptSubmitFields):
    """Kiro's UserPromptSubmit fields."""

    userMessage: str = Field(default="", validation_alias="prompt")


@payload_model(Frontend.KIRO, CanonicalHook.STOP)
class KiroStopFields(StopFields):
    """Kiro's Stop fields."""

    stopHookActive: Flag = Field(default=False, validation_alias="stop_hook_active")


@payload_model(Frontend.KIRO, CanonicalTool.READ)
class KiroReadParams(ToolParams):
    """Kiro's read/fs_read/grep parameters.

    `path` is optional: Kiro omits it entirely when `operations` is absent
    or empty.
    """

    path: str | None = Field(
        default=None, validation_alias=AliasPath("operations", 0, "path")
    )


@payload_model(Frontend.KIRO, CanonicalTool.EDIT)
class KiroEditParams(ToolParams):
    """Kiro's write/fs_write parameters."""

    path: str | None = Field(default=None, validation_alias="path")
    diff: str | None = None

    _diff = model_validator(mode="before")(diff_envelope("newStr", "content"))
