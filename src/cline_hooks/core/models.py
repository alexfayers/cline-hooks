# ruff: noqa: N815
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar, Self, TypeVar, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from cline_hooks.core.vocabulary import CanonicalHook

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

logger = logging.getLogger("hooks")

_HookInputT = TypeVar("_HookInputT", bound="HookInput")


class HookFields(BaseModel):
    """Base class for per-hook payload fields, tolerant of unknown input."""

    model_config = ConfigDict(extra="ignore")


class HookInput(BaseModel):
    """Base class for all hook inputs.

    Subclasses set `hookName` as a class-level default and register
    themselves in `HOOK_INPUTS` via the `hook_input` decorator.
    """

    model_config = ConfigDict(extra="ignore")

    payload_field: ClassVar[str] = ""

    hookName: str
    taskId: str = ""
    workspaceRoots: list[str] = Field(default_factory=list)
    transcriptPath: str = ""
    agentType: str = ""

    @classmethod
    def build(cls, data: Mapping[str, Any]) -> Self:
        """Construct an instance from raw hook data, never raising.

        A malformed known field falls back to `model_construct`, which skips
        validation and coercion and keeps the raw value.

        Args:
            data: The raw hook input data.

        Returns:
            A validated instance, or an unvalidated fallback on failure.
        """
        try:
            return cls.model_validate(dict(data))
        except ValidationError:
            logger.warning("Invalid %s data: %s", cls.__name__, dict(data))
            return cls.model_construct(**dict(data))


class PreToolUseFields(HookFields):
    """Fields specific to PreToolUse hooks."""

    toolName: str
    parameters: dict[str, Any]


class PostToolUseFields(HookFields):
    """Fields specific to PostToolUse hooks."""

    toolName: str
    parameters: dict[str, Any]
    success: bool
    executionTimeMs: int = 0
    result: str | None = None


class TaskStartFields(HookFields):
    """Fields specific to TaskStart hooks."""

    task: str = ""
    source: str = ""


class TaskResumeFields(HookFields):
    """Fields specific to TaskResume hooks."""

    task: str = ""


class TaskCancelFields(HookFields):
    """Fields specific to TaskCancel hooks."""


class TaskCompleteFields(HookFields):
    """Fields specific to TaskComplete hooks."""


class UserPromptSubmitFields(HookFields):
    """Fields specific to UserPromptSubmit hooks."""

    userMessage: str = ""


class PreCompactFields(HookFields):
    """Fields specific to PreCompact hooks."""

    conversationLength: int = 0
    estimatedTokens: int = 0


class StopFields(HookFields):
    """Fields specific to Stop hooks."""

    stopHookActive: bool = False


HOOK_INPUTS: dict[str, type[HookInput]] = {}


def hook_input(hook: CanonicalHook) -> Callable[[type[_HookInputT]], type[_HookInputT]]:
    """Register a HookInput subclass for a canonical hook.

    Derives the payload field name by finding the single field whose
    annotation is a `HookFields` subclass (possibly wrapped in `X | None`).

    Args:
        hook: The canonical hook this input class applies to.

    Returns:
        A decorator that registers the decorated class and returns it unchanged.

    Raises:
        TypeError: If the class does not have exactly one payload field.
    """

    def decorator(cls: type[_HookInputT]) -> type[_HookInputT]:
        HOOK_INPUTS[hook] = cls

        payload_fields: list[str] = []
        for name, field_info in cls.model_fields.items():
            annotation = field_info.annotation
            candidates = get_args(annotation) or (annotation,)
            for candidate in candidates:
                if isinstance(candidate, type) and issubclass(candidate, HookFields):
                    payload_fields.append(name)
                    break

        if len(payload_fields) != 1:
            raise TypeError(
                f"{cls.__name__} must have exactly one HookFields payload field, "
                f"found {len(payload_fields)}"
            )

        cls.payload_field = payload_fields[0]
        return cls

    return decorator


@hook_input(CanonicalHook.PRE_TOOL_USE)
class HookInputPreToolUse(HookInput):
    """Hook input for PreToolUse events."""

    preToolUse: PreToolUseFields | None = None
    hookName: str = "PreToolUse"


@hook_input(CanonicalHook.POST_TOOL_USE)
class HookInputPostToolUse(HookInput):
    """Hook input for PostToolUse events."""

    postToolUse: PostToolUseFields | None = None
    hookName: str = "PostToolUse"


@hook_input(CanonicalHook.TASK_START)
class HookInputTaskStart(HookInput):
    """Hook input for TaskStart events."""

    taskStart: TaskStartFields | None = None
    hookName: str = "TaskStart"


@hook_input(CanonicalHook.TASK_RESUME)
class HookInputTaskResume(HookInput):
    """Hook input for TaskResume events."""

    taskResume: TaskResumeFields | None = None
    hookName: str = "TaskResume"


@hook_input(CanonicalHook.TASK_CANCEL)
class HookInputTaskCancel(HookInput):
    """Hook input for TaskCancel events."""

    taskCancel: TaskCancelFields | None = None
    hookName: str = "TaskCancel"


@hook_input(CanonicalHook.TASK_COMPLETE)
class HookInputTaskComplete(HookInput):
    """Hook input for TaskComplete events."""

    taskComplete: TaskCompleteFields | None = None
    hookName: str = "TaskComplete"


@hook_input(CanonicalHook.USER_PROMPT_SUBMIT)
class HookInputUserPromptSubmit(HookInput):
    """Hook input for UserPromptSubmit events."""

    userPromptSubmit: UserPromptSubmitFields | None = None
    hookName: str = "UserPromptSubmit"


@hook_input(CanonicalHook.PRE_COMPACT)
class HookInputPreCompact(HookInput):
    """Hook input for PreCompact events."""

    preCompact: PreCompactFields | None = None
    hookName: str = "PreCompact"


@hook_input(CanonicalHook.STOP)
class HookInputStop(HookInput):
    """Hook input for Stop events."""

    stop: StopFields | None = None
    hookName: str = "Stop"
