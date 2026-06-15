# ruff: noqa: N815
from __future__ import annotations

from dataclasses import dataclass, field, fields
import json
import logging
from typing import Any

logger = logging.getLogger("hooks")


def inheritors(klass: type) -> set[type]:
    """Return all classes that inherit from the given class.

    Returns:
        set[type]: The inheritors of the given class.
    """
    subclasses: set[type] = set()
    work: list[type] = [klass]
    while work:
        parent = work.pop()
        for child in parent.__subclasses__():
            if child not in subclasses:
                subclasses.add(child)
                work.append(child)
    return subclasses


@dataclass
class HookInput:
    """Base class for all hook inputs.

    Subclasses should set `hookName` as a class-level default to enable
    automatic dispatch in `parse_data`.
    """

    hookName: str
    taskId: str = ""
    workspaceRoots: list[str] = field(default_factory=list)
    transcriptPath: str = ""
    agentType: str = ""


@dataclass
class PreToolUseFields:
    """Fields specific to PreToolUse hooks."""

    toolName: str
    parameters: dict[str, Any]


@dataclass
class PostToolUseFields:
    """Fields specific to PostToolUse hooks."""

    toolName: str
    parameters: dict[str, Any]
    success: bool
    executionTimeMs: int
    result: str | None = None


@dataclass
class TaskStartFields:
    """Fields specific to TaskStart hooks."""

    task: str = ""
    source: str = ""


@dataclass
class TaskResumeFields:
    """Fields specific to TaskResume hooks."""

    task: str = ""


@dataclass
class TaskCancelFields:
    """Fields specific to TaskCancel hooks."""


@dataclass
class TaskCompleteFields:
    """Fields specific to TaskComplete hooks."""


@dataclass
class UserPromptSubmitFields:
    """Fields specific to UserPromptSubmit hooks."""

    userMessage: str = ""


@dataclass
class PreCompactFields:
    """Fields specific to PreCompact hooks."""

    conversationLength: int
    estimatedTokens: int


@dataclass
class HookInputPreToolUse(HookInput):
    """Hook input for PreToolUse events."""

    preToolUse: PreToolUseFields | None = None
    hookName: str = "PreToolUse"

    def __post_init__(self) -> None:
        if isinstance(self.preToolUse, dict):
            self.preToolUse = PreToolUseFields(**_filter_fields(PreToolUseFields, self.preToolUse))


@dataclass
class HookInputPostToolUse(HookInput):
    """Hook input for PostToolUse events."""

    postToolUse: PostToolUseFields | None = None
    hookName: str = "PostToolUse"

    def __post_init__(self) -> None:
        if isinstance(self.postToolUse, dict):
            self.postToolUse = PostToolUseFields(**_filter_fields(PostToolUseFields, self.postToolUse))


@dataclass
class HookInputTaskStart(HookInput):
    """Hook input for TaskStart events."""

    taskStart: TaskStartFields | None = None
    hookName: str = "TaskStart"

    def __post_init__(self) -> None:
        if isinstance(self.taskStart, dict):
            self.taskStart = TaskStartFields(**_filter_fields(TaskStartFields, self.taskStart))


@dataclass
class HookInputTaskResume(HookInput):
    """Hook input for TaskResume events."""

    taskResume: TaskResumeFields | None = None
    hookName: str = "TaskResume"

    def __post_init__(self) -> None:
        if isinstance(self.taskResume, dict):
            self.taskResume = TaskResumeFields(**_filter_fields(TaskResumeFields, self.taskResume))


@dataclass
class HookInputTaskCancel(HookInput):
    """Hook input for TaskCancel events."""

    taskCancel: TaskCancelFields | None = None
    hookName: str = "TaskCancel"

    def __post_init__(self) -> None:
        if isinstance(self.taskCancel, dict):
            self.taskCancel = TaskCancelFields(**_filter_fields(TaskCancelFields, self.taskCancel))


@dataclass
class HookInputTaskComplete(HookInput):
    """Hook input for TaskComplete events."""

    taskComplete: TaskCompleteFields | None = None
    hookName: str = "TaskComplete"

    def __post_init__(self) -> None:
        if isinstance(self.taskComplete, dict):
            self.taskComplete = TaskCompleteFields(**_filter_fields(TaskCompleteFields, self.taskComplete))


@dataclass
class HookInputUserPromptSubmit(HookInput):
    """Hook input for UserPromptSubmit events."""

    userPromptSubmit: UserPromptSubmitFields | None = None
    hookName: str = "UserPromptSubmit"

    def __post_init__(self) -> None:
        if isinstance(self.userPromptSubmit, dict):
            self.userPromptSubmit = UserPromptSubmitFields(
                **_filter_fields(UserPromptSubmitFields, self.userPromptSubmit)
            )


@dataclass
class HookInputPreCompact(HookInput):
    """Hook input for PreCompact events."""

    preCompact: PreCompactFields | None = None
    hookName: str = "PreCompact"

    def __post_init__(self) -> None:
        if isinstance(self.preCompact, dict):
            self.preCompact = PreCompactFields(**_filter_fields(PreCompactFields, self.preCompact))


@dataclass
class McpToolUse:
    """Parsed MCP tool use from use_mcp_tool parameters."""

    server_name: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    task_progress: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.arguments, str):
            try:
                self.arguments = json.loads(self.arguments)
            except json.JSONDecodeError:
                logger.warning("Failed to parse MCP arguments as JSON: %s", self.arguments)

        if not self.arguments:
            logger.warning("No arguments found for tool %s", self.tool_name)
            self.arguments = {}


def _filter_fields(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    """Return only keys from data that are valid fields for the given dataclass.

    Args:
        cls: The dataclass type to filter for.
        data: The raw input dictionary.

    Returns:
        A dict containing only the keys accepted by cls.
    """
    known = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in known}
