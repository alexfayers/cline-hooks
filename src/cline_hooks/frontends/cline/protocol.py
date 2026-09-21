# ruff: file-ignore[print]
"""Cline JSON stdout protocol."""

from __future__ import annotations

import json
import logging
import sys
from typing import TYPE_CHECKING, Any, ClassVar, NoReturn

from cline_hooks.core.frontend import EXACT_MATCH, frontend
from cline_hooks.core.models import HOOK_INPUTS, HookInput
from cline_hooks.core.outcome import Disposition
from cline_hooks.core.protocol import HookRegistration, Protocol
from cline_hooks.core.response import Response
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool
from cline_hooks.frontends.cline.install import ClineInstaller

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cline_hooks.core.outcome import Outcome
    from cline_hooks.core.protocol import RawPayload

_TOOL_HOOK_KEYS = ("preToolUse", "postToolUse")


@frontend(
    name="cline",
    display_name="Cline",
    installer=ClineInstaller(),
    detect_priority=EXACT_MATCH,
    default=True,
)
class ClineProtocol(Protocol):
    """Cline JSON stdout protocol.

    The canonical vocabulary is Cline's own, so parsing only renames the few
    tools Cline names differently.
    """

    supported_hooks: ClassVar[Mapping[CanonicalHook, HookRegistration]] = {
        CanonicalHook.PRE_TOOL_USE: HookRegistration("PreToolUse"),
        CanonicalHook.POST_TOOL_USE: HookRegistration("PostToolUse"),
        CanonicalHook.TASK_START: HookRegistration("TaskStart"),
        CanonicalHook.TASK_RESUME: HookRegistration("TaskResume"),
        CanonicalHook.TASK_CANCEL: HookRegistration("TaskCancel"),
        CanonicalHook.TASK_COMPLETE: HookRegistration("TaskComplete"),
        CanonicalHook.USER_PROMPT_SUBMIT: HookRegistration("UserPromptSubmit"),
        CanonicalHook.PRE_COMPACT: HookRegistration("PreCompact"),
        CanonicalHook.STOP: HookRegistration("Stop"),
    }
    tool_map: ClassVar[Mapping[str, CanonicalTool]] = {
        "new_task": CanonicalTool.SPAWN_AGENT,
        "subagent": CanonicalTool.SPAWN_AGENT,
    }

    @classmethod
    def detect(cls, payload: RawPayload) -> bool:
        """Return True if the payload carries Cline's native `hookName` key."""
        return payload.data is not None and "hookName" in payload.data

    def parse(self, payload: RawPayload) -> HookInput:
        """Parse Cline's native JSON payload into the most specific HookInput subclass.

        Returns:
            The parsed HookInput subclass matching the payload's hook name.
        """
        data: dict[str, Any] = payload.data if payload.data is not None else json.loads(payload.raw)
        for key in _TOOL_HOOK_KEYS:
            fields = data.get(key)
            if isinstance(fields, dict) and (native := fields.get("toolName")):
                data = {
                    **data,
                    key: {**fields, "toolName": self.tool_map.get(native, native)},
                }
        input_class = HOOK_INPUTS.get(data.get("hookName", ""), HookInput)
        return input_class.build(data)

    def configure_logging(self) -> None:
        """Also stream hook logs to stderr, since Cline surfaces no other channel for them."""
        logging.getLogger("hooks").addHandler(logging.StreamHandler())

    def allow(self, message: str | None = None, *, system_message: str | None = None) -> NoReturn:
        """Allow via JSON stdout."""
        res: dict[str, object] = {"cancel": False}
        if message is not None:
            res["contextModification"] = message
        print(json.dumps(res), end="")
        sys.exit(0)

    def block(self, message: str) -> NoReturn:
        """Block via JSON stdout."""
        res: dict[str, object] = {"cancel": True, "errorMessage": message}
        print(json.dumps(res), end="")
        sys.exit(0)

    def render(self, outcome: Outcome) -> Response:
        """Render the outcome as Cline's JSON stdout contract.

        Returns:
            The rendered Response.
        """
        if outcome.disposition in {Disposition.BLOCK, Disposition.FEEDBACK}:
            res: dict[str, object] = {"cancel": True, "errorMessage": outcome.message or ""}
            return Response(stdout=json.dumps(res))
        message = outcome.message
        if message is not None and outcome.label:
            message = f"{outcome.label}: {message}"
        res = {"cancel": False}
        if message is not None:
            res["contextModification"] = message
        return Response(stdout=json.dumps(res))
