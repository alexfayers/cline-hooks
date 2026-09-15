"""Antigravity's payload models: where its raw hook JSON differs from canonical."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from cline_hooks.core.models import PostToolUseFields, StopFields
from cline_hooks.core.payload import PayloadEnvelope, ToolParams, diff_envelope


def _outcome_from_error(data: dict[str, Any]) -> dict[str, Any]:
    """Derive a finished tool call's outcome from Antigravity's error string.

    Returns:
        The data with `success` and `result` set from `error`.
    """
    error = data.get("error") or ""
    return {**data, "success": not error, "result": error or None}


class AntigravityEnvelope(PayloadEnvelope):
    """Antigravity's envelope fields, which every event carries.

    Every key is redeclared because Antigravity names them in camelCase, and
    because `workspacePaths` is already a list of roots rather than one cwd.
    """

    taskId: str = Field(default="", validation_alias="conversationId")
    workspaceRoots: list[str] = Field(
        default_factory=list, validation_alias="workspacePaths"
    )
    transcriptPath: str = Field(default="", validation_alias="transcriptPath")
    agentType: str = Field(default="", validation_alias="modelName")


class AntigravityPostToolUse(PostToolUseFields):
    """Antigravity's PostToolUse fields.

    A finished call's outcome is reported only as an error string, empty where
    the call succeeded, and its duration not at all.
    """

    _outcome = model_validator(mode="before")(_outcome_from_error)


class AntigravityStop(StopFields):
    """Antigravity's Stop fields; it documents no stop-hook re-entry flag."""


class AntigravityReadParams(ToolParams):
    """Antigravity's view_file parameters, carrying its optional line range."""

    path: str | None = Field(default=None, validation_alias="AbsolutePath")
    start_line: int | None = Field(default=None, validation_alias="StartLine")
    end_line: int | None = Field(default=None, validation_alias="EndLine")


class AntigravityEditWriteParams(ToolParams):
    """Antigravity's file write and edit parameters.

    `multi_replace_file_content` carries its edits as chunks in a shape
    Antigravity does not document, so it normalises to a path alone.
    """

    path: str | None = Field(default=None, validation_alias="TargetFile")
    diff: str | None = None

    _diff = model_validator(mode="before")(
        diff_envelope("ReplacementContent", "CodeContent")
    )


class AntigravityShellParams(ToolParams):
    """Antigravity's run_command parameters."""

    command: str = Field(default="", validation_alias="CommandLine")


class AntigravityWebParams(ToolParams):
    """Antigravity's web fetch and search parameters."""

    url: str | None = Field(default=None, validation_alias="Url")
    query: str | None = None
