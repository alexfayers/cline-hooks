"""Pi's payload models: where the bridge extension's hook JSON differs from canonical."""

from __future__ import annotations

import re
from typing import Any

from pydantic import Field, field_validator, model_validator

from cline_hooks.core.models import PostToolUseFields, StopFields, TaskStartFields, UserPromptSubmitFields
from cline_hooks.core.payload import Flag, PayloadEnvelope, ToolParams, diff_envelope, line_range
from cline_hooks.core.vocabulary import TaskSource

# Pi's session_start reasons that continue an existing conversation.
_RESUMING_REASONS = frozenset({"reload", "fork"})

# pi-subagents names a child session `<agent type>#<first 8 hex chars of its agent id>`.
_SUBAGENT_SESSION_NAME = re.compile(r"(?P<agent_type>.+)#(?P<agent_id>[0-9a-f]{8})")


class PiEnvelope(PayloadEnvelope):
    """Pi's envelope fields; a subagent's type and id come from its `session_name`."""

    @model_validator(mode="before")
    @classmethod
    def _subagent_identity(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Set `agent_type` and `agent_id` from a pi-subagents child session name.

        Returns:
            The data with the subagent's type and id set, where the session is a child.
        """
        match = _SUBAGENT_SESSION_NAME.fullmatch(str(data.get("session_name") or ""))
        return {**data, **match.groupdict()} if match else data


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


class PiPostToolUse(PostToolUseFields):
    """Pi's PostToolUse fields; the context usage is as the bridge reports it."""

    contextWindow: int | None = Field(default=None, validation_alias="context_window")
    contextTokens: int | None = Field(default=None, validation_alias="context_tokens")

    def frontend_kwargs(self) -> dict[str, object]:
        """Extra plugin dispatch kwargs a frontend derives from its own payload.

        Returns:
            The model's context window and the tokens in use, each None where the bridge reports none.
        """
        return {"context_window": self.contextWindow, "context_tokens": self.contextTokens}


class PiUserPromptSubmit(UserPromptSubmitFields):
    """Pi's UserPromptSubmit fields; `userMessage` comes from `prompt`, the context usage from the bridge."""

    userMessage: str = Field(default="", validation_alias="prompt")
    contextWindow: int | None = Field(default=None, validation_alias="context_window")
    contextTokens: int | None = Field(default=None, validation_alias="context_tokens")

    def frontend_kwargs(self) -> dict[str, object]:
        """Extra plugin dispatch kwargs a frontend derives from its own payload.

        Returns:
            The model's context window and the tokens in use, each None where the bridge reports none.
        """
        return {"context_window": self.contextWindow, "context_tokens": self.contextTokens}


class PiStop(StopFields):
    """Pi's Stop fields; `stopHookActive` comes from `stop_hook_active`."""

    stopHookActive: Flag = Field(default=False, validation_alias="stop_hook_active")


class PiReadParams(ToolParams):
    """Parameters for a pi `read` tool call; `offset`/`limit` become a line range."""

    path: str = ""
    start_line: int | None = None
    end_line: int | None = None

    _line_range = model_validator(mode="before")(line_range)


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
