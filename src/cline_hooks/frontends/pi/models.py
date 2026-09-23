"""Pi's payload models: where the bridge extension's hook JSON differs from canonical."""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from cline_hooks.core.models import StopFields, TaskStartFields, UserPromptSubmitFields
from cline_hooks.core.payload import Flag, ToolParams, diff_envelope
from cline_hooks.core.vocabulary import TaskSource

# Pi's session_start reasons that continue an existing conversation.
_RESUMING_REASONS = frozenset({"reload", "fork"})


class PiTaskStart(TaskStartFields):
    """Pi's TaskStart fields; `source` is pi's session_start reason.

    `reload` and `fork` keep the conversation so far, so they map to resume.
    """

    source: str = ""

    @field_validator("source")
    @classmethod
    def _canonical_source(cls, value: str) -> str:
        """Map a pi session_start reason onto the canonical task source.

        Returns:
            `resume` for a reason that keeps the conversation, else the reason.
        """
        return TaskSource.RESUME if value in _RESUMING_REASONS else value


class PiUserPromptSubmit(UserPromptSubmitFields):
    """Pi's UserPromptSubmit fields; `userMessage` comes from `prompt`."""

    userMessage: str = Field(default="", validation_alias="prompt")


class PiStop(StopFields):
    """Pi's Stop fields; `stopHookActive` comes from `stop_hook_active`."""

    stopHookActive: Flag = Field(default=False, validation_alias="stop_hook_active")


class PiReadParams(ToolParams):
    """Parameters for a pi `read` tool call; `offset`/`limit` become a line range."""

    path: str = ""
    start_line: int | None = None
    end_line: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _line_range(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Convert pi's 1-indexed `offset` and `limit` into start and end lines.

        Returns:
            The data with `start_line`/`end_line` set where pi bounds the read.
        """
        offset = data.get("offset")
        limit = data.get("limit")
        if not isinstance(limit, int):
            return {**data, "start_line": offset}
        start = offset if isinstance(offset, int) else 1
        return {**data, "start_line": start, "end_line": start + limit - 1}


class PiWriteParams(ToolParams):
    """Parameters for a pi `write` tool call."""

    path: str | None = None
    diff: str | None = None

    _diff = model_validator(mode="before")(diff_envelope("content"))


class PiEditParams(ToolParams):
    """Parameters for a pi `edit` tool call, whose `edits` hold oldText/newText pairs."""

    path: str | None = None
    diff: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _diff(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Render every replacement as one SEARCH/REPLACE block.

        Returns:
            The data with `diff` set, where there are edits.
        """
        edits = [edit for edit in data.get("edits") or [] if isinstance(edit, dict)]
        if not edits:
            return data
        blocks = [
            f"------- SEARCH\n{edit.get('oldText', '')}\n=======\n{edit.get('newText', '')}\n+++++++ REPLACE"
            for edit in edits
        ]
        return {**data, "diff": "\n".join(blocks)}
