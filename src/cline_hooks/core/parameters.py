"""Canonical per-tool parameter models and their registry."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Self, TypeVar

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    field_validator,
)

from cline_hooks.core.vocabulary import CanonicalTool

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

logger = logging.getLogger("hooks.parameters")

_ModelT = TypeVar("_ModelT", bound="ToolParameters")


class ToolParameters(BaseModel):
    """Base model for a tool's parameters, tolerant of unknown or malformed input."""

    model_config = ConfigDict(extra="allow")

    @classmethod
    def build(cls, parameters: Mapping[str, Any]) -> Self:
        """Construct an instance from raw parameters, never raising.

        A malformed known field falls back to `model_construct`, which skips
        validation and coercion and keeps the raw value.

        Args:
            parameters: The raw tool parameters.

        Returns:
            A validated instance, or an unvalidated fallback on failure.
        """
        try:
            return cls.model_validate(dict(parameters))
        except ValidationError:
            logger.warning("Invalid %s parameters: %s", cls.__name__, dict(parameters))
            return cls.model_construct(**dict(parameters))


PARAMETER_MODELS: dict[str, type[ToolParameters]] = {}


def parameter_model(
    *tools: CanonicalTool,
) -> Callable[[type[_ModelT]], type[_ModelT]]:
    """Register a parameter model for one or more canonical tools.

    Args:
        *tools: The canonical tools this model applies to.

    Returns:
        A decorator that registers the decorated class and returns it unchanged.
    """

    def decorator(cls: type[_ModelT]) -> type[_ModelT]:
        for tool in tools:
            PARAMETER_MODELS[tool] = cls
        return cls

    return decorator


def parameters_for(tool_name: str, parameters: Mapping[str, Any]) -> ToolParameters:
    """Build the registered parameter model for a tool, or a bare fallback.

    Args:
        tool_name: The canonical tool name.
        parameters: The raw tool parameters.

    Returns:
        The built parameter model.
    """
    return PARAMETER_MODELS.get(tool_name, ToolParameters).build(parameters)


@parameter_model(CanonicalTool.SHELL)
class ShellParameters(ToolParameters):
    """Parameters for a shell command execution tool call."""

    command: str = ""


@parameter_model(CanonicalTool.READ)
class ReadParameters(ToolParameters):
    """Parameters for a file read tool call."""

    path: str = Field(default="", validation_alias=AliasChoices("path", "file_path"))
    start_line: int | None = None
    end_line: int | None = None


@parameter_model(CanonicalTool.EDIT, CanonicalTool.WRITE)
class FileEditParameters(ToolParameters):
    """Parameters for a file edit or write tool call."""

    path: str = ""
    diff: str = ""


@parameter_model(CanonicalTool.SKILL)
class SkillParameters(ToolParameters):
    """Parameters for a skill invocation tool call."""

    skill: str = Field(default="", validation_alias=AliasChoices("skill_name", "skill"))


@parameter_model(CanonicalTool.PLAN_MODE_RESPOND)
class PlanModeRespondParameters(ToolParameters):
    """Parameters for a plan-mode response tool call."""

    response: str = ""


@parameter_model(CanonicalTool.ATTEMPT_COMPLETION)
class AttemptCompletionParameters(ToolParameters):
    """Parameters for an attempt-completion tool call."""

    task_progress: str = ""


@parameter_model(CanonicalTool.WEB_FETCH, CanonicalTool.WEB_SEARCH)
class WebResearchParameters(ToolParameters):
    """Parameters for a web fetch or web search tool call."""

    url: str = ""
    query: str = ""


@parameter_model(CanonicalTool.MCP)
class McpToolUse(ToolParameters):
    """Parsed MCP tool use from use_mcp_tool parameters."""

    server_name: str = ""
    tool_name: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict, validate_default=True)
    task_progress: str | None = None

    @field_validator("arguments", mode="before")
    @classmethod
    def _parse_arguments(cls, value: Any, info: ValidationInfo) -> Any:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                logger.warning("Failed to parse MCP arguments as JSON: %s", value)
                value = {}

        if not value:
            logger.warning("No arguments found for tool %s", info.data.get("tool_name", ""))
            return {}
        return value
