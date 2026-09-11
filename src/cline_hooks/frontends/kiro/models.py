"""Kiro's payload models: where its raw hook JSON differs from canonical."""

from __future__ import annotations

from pydantic import AliasPath, Field, model_validator

from cline_hooks.core.models import StopFields, TaskStartFields, UserPromptSubmitFields
from cline_hooks.core.payload import Flag, ToolParams, diff_envelope


class KiroTaskStartFields(TaskStartFields):
    """Kiro's TaskStart fields."""

    source: str = ""


class KiroUserPromptSubmitFields(UserPromptSubmitFields):
    """Kiro's UserPromptSubmit fields."""

    userMessage: str = Field(default="", validation_alias="prompt")


class KiroStopFields(StopFields):
    """Kiro's Stop fields."""

    stopHookActive: Flag = Field(default=False, validation_alias="stop_hook_active")


class KiroReadParams(ToolParams):
    """Kiro's read/fs_read/grep parameters.

    `path` is optional: Kiro omits it entirely when `operations` is absent
    or empty.
    """

    path: str | None = Field(
        default=None, validation_alias=AliasPath("operations", 0, "path")
    )


class KiroEditParams(ToolParams):
    """Kiro's write/fs_write parameters."""

    path: str | None = Field(default=None, validation_alias="path")
    diff: str | None = None

    _diff = model_validator(mode="before")(diff_envelope("newStr", "content"))
