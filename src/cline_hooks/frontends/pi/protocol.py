"""Pi exit-code protocol, spoken by the bridge extension `PiInstaller` writes."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, NoReturn

from cline_hooks.core.frontend import EXACT_MATCH, frontend
from cline_hooks.core.payload import PayloadEnvelope, StandardPayloadProtocol, ToolParams
from cline_hooks.core.protocol import HookRegistration, exit_allow, exit_block
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool
from cline_hooks.frontends.copilot.models import CopilotPreCompact
from cline_hooks.frontends.pi.install import PiInstaller, agent_dir
from cline_hooks.frontends.pi.models import (
    PiEditParams,
    PiEnvelope,
    PiPostToolUse,
    PiReadParams,
    PiStop,
    PiTaskStart,
    PiUserPromptSubmit,
    PiWriteParams,
)
from cline_hooks.frontends.pi.transcript import PiTranscriptReader

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cline_hooks.core.models import HookFields
    from cline_hooks.core.protocol import RawPayload
    from cline_hooks.core.transcript import TranscriptReader


@frontend(
    name="pi",
    display_name="Pi",
    installer=PiInstaller(),
    detect_priority=EXACT_MATCH,
    skills_dir=lambda: agent_dir() / "skills",
)
class PiProtocol(StandardPayloadProtocol):
    """Pi exit-code protocol: exit 0 + stdout for context, exit 2 + stderr to block.

    Pi has no command hooks, only TypeScript extension events, so the bridge
    extension relays each event as snake_case JSON named after the pi event,
    and maps the exit code back onto that event's own result. MCP tools are
    named `mcp__<server>__<tool>` (pi core) or, for pi-mcp-adapter direct tools,
    `mcp__<server>_<tool>`, so a name without `__` splits at its first `_`.
    """

    supported_hooks: ClassVar[Mapping[CanonicalHook, HookRegistration]] = {
        CanonicalHook.PRE_TOOL_USE: HookRegistration("tool_call"),
        CanonicalHook.POST_TOOL_USE: HookRegistration("tool_result"),
        CanonicalHook.TASK_START: HookRegistration("session_start"),
        CanonicalHook.USER_PROMPT_SUBMIT: HookRegistration("before_agent_start"),
        CanonicalHook.PRE_COMPACT: HookRegistration("session_before_compact"),
        CanonicalHook.STOP: HookRegistration("agent_end"),
        CanonicalHook.SUBAGENT_STOP: HookRegistration("session_shutdown"),
    }
    tool_map: ClassVar[Mapping[str, CanonicalTool]] = {
        "delegate_agent": CanonicalTool.SPAWN_AGENT,
        "continue_agent": CanonicalTool.SPAWN_AGENT,
        "bash": CanonicalTool.SHELL,
        "read": CanonicalTool.READ,
        "edit": CanonicalTool.EDIT,
        "write": CanonicalTool.WRITE,
        "Agent": CanonicalTool.SPAWN_AGENT,
        "SubagentWorkflow": CanonicalTool.SPAWN_AGENT,
        "plan_mode_complete": CanonicalTool.PLAN_MODE_RESPOND,
        "fetch_content": CanonicalTool.WEB_FETCH,
        "get_search_content": CanonicalTool.WEB_FETCH,
        "source_check": CanonicalTool.WEB_SEARCH,
    }
    envelope_model: ClassVar[type[PayloadEnvelope]] = PiEnvelope
    hook_models: ClassVar[Mapping[CanonicalHook, type[HookFields]]] = {
        CanonicalHook.POST_TOOL_USE: PiPostToolUse,
        CanonicalHook.TASK_START: PiTaskStart,
        CanonicalHook.USER_PROMPT_SUBMIT: PiUserPromptSubmit,
        CanonicalHook.PRE_COMPACT: CopilotPreCompact,
        CanonicalHook.STOP: PiStop,
        CanonicalHook.SUBAGENT_STOP: PiStop,
    }
    tool_models: ClassVar[Mapping[CanonicalTool, type[ToolParams]]] = {
        CanonicalTool.READ: PiReadParams,
        CanonicalTool.EDIT: PiEditParams,
        CanonicalTool.WRITE: PiWriteParams,
    }
    transcript: ClassVar[TranscriptReader] = PiTranscriptReader()
    mcp_prefix: ClassVar[str] = "mcp__"
    mcp_separators: ClassVar[tuple[str, ...]] = ("__", "_")

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
