"""Opencode's payload models: where the bridge plugin's tool input differs from canonical."""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from cline_hooks.core.payload import ToolParams, diff_envelope, line_range


class OpencodeReadParams(ToolParams):
    """Parameters for an opencode `read` tool call; `offset`/`limit` become a line range."""

    path: str = Field(default="", validation_alias="filePath")
    start_line: int | None = None
    end_line: int | None = None

    _line_range = model_validator(mode="before")(line_range)


class OpencodeWriteParams(ToolParams):
    """Parameters for an opencode `write` tool call."""

    path: str | None = Field(default=None, validation_alias="filePath")
    diff: str | None = None

    _diff = model_validator(mode="before")(diff_envelope("content"))


class OpencodeEditParams(ToolParams):
    """Parameters for an opencode `edit` tool call, whose `oldString`/`newString` become one SEARCH/REPLACE block."""

    path: str | None = Field(default=None, validation_alias="filePath")
    diff: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _diff(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Render the replacement as a SEARCH/REPLACE block.

        Returns:
            The data with `diff` set, where there is a replacement.
        """
        if "newString" not in data:
            return data
        diff = f"------- SEARCH\n{data.get('oldString', '')}\n=======\n{data['newString']}\n+++++++ REPLACE"
        return {**data, "diff": diff}


class OpencodeSkillParams(ToolParams):
    """Parameters for an opencode `skill` tool call, which names the skill as `name`."""

    skill: str = Field(default="", validation_alias="name")
