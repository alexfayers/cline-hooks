"""Pi exit-code protocol, spoken by the bridge extension `PiInstaller` writes."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, NoReturn

from cline_hooks.core.frontend import EXACT_MATCH, frontend
from cline_hooks.core.payload import StandardPayloadProtocol, ToolParams
from cline_hooks.core.protocol import HookRegistration, exit_allow, exit_block
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool
from cline_hooks.frontends.copilot.models import CopilotPreCompact
from cline_hooks.frontends.pi.install import PiInstaller
from cline_hooks.frontends.pi.models import (
    PiEditParams,
    PiReadParams,
    PiStop,
    PiTaskStart,
    PiUserPromptSubmit,
    PiWriteParams,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cline_hooks.core.models import HookFields
    from cline_hooks.core.protocol import RawPayload


@frontend(
    name="pi",
    display_name="Pi",
    installer=PiInstaller(),
    detect_priority=EXACT_MATCH,
)
class PiProtocol(StandardPayloadProtocol):
    """Pi exit-code protocol: exit 0 + stdout for context, exit 2 + stderr to block.

    Pi has no command hooks, only TypeScript extension events, so the bridge
    extension relays each event as snake_case JSON named after the pi event,
    and maps the exit code back onto that event's own result. MCP tools are
    pi-mcp-adapter direct tools under its `mcp` tool prefix,
    `mcp__<server>_<tool>`, so a server name holding `_` splits at its first.
    """

    supported_hooks: ClassVar[Mapping[CanonicalHook, HookRegistration]] = {
        CanonicalHook.PRE_TOOL_USE: HookRegistration("tool_call"),
        CanonicalHook.POST_TOOL_USE: HookRegistration("tool_result"),
        CanonicalHook.TASK_START: HookRegistration("session_start"),
        CanonicalHook.USER_PROMPT_SUBMIT: HookRegistration("before_agent_start"),
        CanonicalHook.PRE_COMPACT: HookRegistration("session_before_compact"),
        CanonicalHook.STOP: HookRegistration("agent_end"),
    }
    tool_map: ClassVar[Mapping[str, CanonicalTool]] = {
        "bash": CanonicalTool.SHELL,
        "read": CanonicalTool.READ,
        "edit": CanonicalTool.EDIT,
        "write": CanonicalTool.WRITE,
    }
    hook_models: ClassVar[Mapping[CanonicalHook, type[HookFields]]] = {
        CanonicalHook.TASK_START: PiTaskStart,
        CanonicalHook.USER_PROMPT_SUBMIT: PiUserPromptSubmit,
        CanonicalHook.PRE_COMPACT: CopilotPreCompact,
        CanonicalHook.STOP: PiStop,
    }
    tool_models: ClassVar[Mapping[CanonicalTool, type[ToolParams]]] = {
        CanonicalTool.READ: PiReadParams,
        CanonicalTool.EDIT: PiEditParams,
        CanonicalTool.WRITE: PiWriteParams,
    }
    mcp_prefix: ClassVar[str] = "mcp__"
    mcp_separator: ClassVar[str] = "_"

    @classmethod
    def detect(cls, payload: RawPayload) -> bool:
        """Detect the bridge extension's payload by its pi event name.

        Returns:
            True if `hook_event_name` is one of pi's own event names.
        """
        data = payload.data
        if data is None:
            return False
        return data.get(cls.hook_event_key) in cls.native_hook_names()

    def allow(self, message: str | None = None, *, system_message: str | None = None) -> NoReturn:
        """Allow via exit 0, context on stdout."""
        exit_allow(message)

    def block(self, message: str) -> NoReturn:
        """Block via exit 2, error on stderr."""
        exit_block(message)
