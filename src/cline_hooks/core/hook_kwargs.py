"""Typed pydantic models for plugin dispatch kwargs shapes."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger("hooks")


class HookKwargs(BaseModel):
    """Base model for a plugin dispatch's kwargs, tolerant of unknown or malformed input."""

    model_config = ConfigDict(extra="ignore")

    @classmethod
    def build(cls, kwargs: Mapping[str, Any]) -> Self:
        """Construct an instance from raw dispatch kwargs, never raising.

        A malformed known field falls back to `model_construct`, which skips
        validation and coercion and keeps the raw value.

        Args:
            kwargs: The raw keyword arguments passed to on_hook.

        Returns:
            A validated instance, or an unvalidated fallback on failure.
        """
        try:
            return cls.model_validate(dict(kwargs))
        except ValidationError:
            logger.warning("Invalid %s kwargs: %s", cls.__name__, dict(kwargs))
            return cls.model_construct(**dict(kwargs))


class PreToolUseKwargs(HookKwargs):
    """Typed kwargs for the generic PreToolUse dispatch."""

    task_id: str = ""
    tool_name: str = ""
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    workspace_roots: list[str] = Field(default_factory=list)
    agent_type: str = ""


class PreShellKwargs(HookKwargs):
    """Typed kwargs for the PreShell plugin scope."""

    task_id: str = ""
    tool_name: str = ""
    command: str = ""
    workspace_roots: list[str] = Field(default_factory=list)
    agent_type: str = ""


class TrackToolUseKwargs(HookKwargs):
    """Typed kwargs for the TrackToolUse plugin scope."""

    task_id: str = ""
    tool_name: str = ""
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    is_state_write: bool = False
    mcp_tool_name: str | None = None
    workspace_roots: list[str] = Field(default_factory=list)
    agent_type: str = ""


class ToolFailedKwargs(HookKwargs):
    """Typed kwargs for the ToolFailed plugin scope."""

    task_id: str = ""
    tool_name: str = ""
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    workspace_roots: list[str] = Field(default_factory=list)
    agent_type: str = ""
