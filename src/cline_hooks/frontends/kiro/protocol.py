"""Kiro exit-code protocol."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, ClassVar

from cline_hooks.core.frontend import EXACT_MATCH, frontend
from cline_hooks.core.outcome import Disposition
from cline_hooks.core.payload import StandardPayloadProtocol, ToolParams
from cline_hooks.core.protocol import HookRegistration
from cline_hooks.core.response import Response
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool
from cline_hooks.frontends.kiro.install import KiroInstaller
from cline_hooks.frontends.kiro.models import (
    KiroEditParams,
    KiroReadParams,
    KiroStopFields,
    KiroTaskStartFields,
    KiroUserPromptSubmitFields,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cline_hooks.core.models import HookFields
    from cline_hooks.core.outcome import Outcome
    from cline_hooks.core.protocol import RawPayload


@frontend(
    name="kiro",
    display_name="Kiro",
    installer=KiroInstaller(),
    detect_priority=EXACT_MATCH,
)
class KiroProtocol(StandardPayloadProtocol):
    """Kiro exit-code protocol: exit 0 + stdout for allow, exit 2 + stderr for block."""

    supported_hooks: ClassVar[Mapping[CanonicalHook, HookRegistration]] = {
        CanonicalHook.PRE_TOOL_USE: HookRegistration("preToolUse", "*"),
        CanonicalHook.POST_TOOL_USE: HookRegistration("postToolUse", "*"),
        CanonicalHook.TASK_START: HookRegistration("agentSpawn"),
        CanonicalHook.USER_PROMPT_SUBMIT: HookRegistration("userPromptSubmit"),
        CanonicalHook.STOP: HookRegistration("stop"),
    }
    tool_map: ClassVar[Mapping[str, CanonicalTool]] = {
        "shell": CanonicalTool.SHELL,
        "execute_bash": CanonicalTool.SHELL,
        "read": CanonicalTool.READ,
        "fs_read": CanonicalTool.READ,
        "write": CanonicalTool.EDIT,
        "fs_write": CanonicalTool.EDIT,
        "grep": CanonicalTool.READ,
        "use_aws": CanonicalTool.SHELL,
        "call_aws": CanonicalTool.SHELL,
    }
    hook_models: ClassVar[Mapping[CanonicalHook, type[HookFields]]] = {
        CanonicalHook.TASK_START: KiroTaskStartFields,
        CanonicalHook.USER_PROMPT_SUBMIT: KiroUserPromptSubmitFields,
        CanonicalHook.STOP: KiroStopFields,
    }
    tool_models: ClassVar[Mapping[CanonicalTool, type[ToolParams]]] = {
        CanonicalTool.READ: KiroReadParams,
        CanonicalTool.EDIT: KiroEditParams,
    }
    session_env_keys: ClassVar[tuple[str, ...]] = ("KIRO_SESSION_ID",)
    mcp_prefix: ClassVar[str] = "@"
    mcp_separators: ClassVar[tuple[str, ...]] = ("/",)

    @classmethod
    def detect(cls, payload: RawPayload) -> bool:
        """Detect Kiro's hook JSON shape.

        Returns:
            True if `hook_event_name` matches one of Kiro's own native hook names.
        """
        data = payload.data
        if data is None:
            return False
        return data.get(cls.hook_event_key) in cls.native_hook_names()

    def render(self, outcome: Outcome) -> Response:
        """Render feedback as Stop's decision JSON, otherwise via the plain exit-code contract.

        Kiro's `Stop` hook only surfaces feedback via decision JSON (see
        kiro.dev/docs/cli/hooks/#stop), so a plain exit-2 block would be a no-op there.

        Returns:
            The rendered Response.
        """
        if outcome.disposition is Disposition.FEEDBACK:
            return Response(stdout=json.dumps({"decision": "block", "reason": outcome.message or ""}))
        return super().render(outcome)
