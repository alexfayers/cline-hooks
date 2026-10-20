"""Pi exit-code protocol, spoken by the bridge extension `PiInstaller` writes."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar, NoReturn

from cline_hooks.core.deferred import deferred
from cline_hooks.core.frontend import EXACT_MATCH, frontend
from cline_hooks.core.payload import PayloadEnvelope, StandardPayloadProtocol, ToolParams
from cline_hooks.core.protocol import HookRegistration, exit_allow, exit_block
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from cline_hooks.core.install import Installer
    from cline_hooks.core.models import HookFields
    from cline_hooks.core.protocol import RawPayload
    from cline_hooks.core.transcript import TranscriptReader


def _skills_dir() -> Path:
    from cline_hooks.frontends.pi.install import agent_dir  # ruff: ignore[import-outside-top-level]

    return agent_dir() / "skills"


def _installer() -> Installer:
    from cline_hooks.frontends.pi.install import PiInstaller  # ruff: ignore[import-outside-top-level]

    return PiInstaller()


def _envelope_model() -> type[PayloadEnvelope]:
    from cline_hooks.frontends.pi.models import PiEnvelope  # ruff: ignore[import-outside-top-level]

    return PiEnvelope


def _hook_models() -> Mapping[CanonicalHook, type[HookFields]]:
    from cline_hooks.frontends.copilot.models import CopilotPreCompact  # ruff: ignore[import-outside-top-level]
    from cline_hooks.frontends.pi.models import (  # ruff: ignore[import-outside-top-level]
        PiPostToolUse,
        PiStop,
        PiTaskStart,
        PiUserPromptSubmit,
    )

    return {
        CanonicalHook.POST_TOOL_USE: PiPostToolUse,
        CanonicalHook.TASK_START: PiTaskStart,
        CanonicalHook.USER_PROMPT_SUBMIT: PiUserPromptSubmit,
        CanonicalHook.PRE_COMPACT: CopilotPreCompact,
        CanonicalHook.STOP: PiStop,
        CanonicalHook.SUBAGENT_STOP: PiStop,
    }


def _tool_models() -> Mapping[CanonicalTool, type[ToolParams]]:
    from cline_hooks.frontends.pi.models import (  # ruff: ignore[import-outside-top-level]
        PiEditParams,
        PiReadParams,
        PiWriteParams,
    )

    return {
        CanonicalTool.READ: PiReadParams,
        CanonicalTool.EDIT: PiEditParams,
        CanonicalTool.WRITE: PiWriteParams,
    }


def _transcript() -> TranscriptReader:
    from cline_hooks.frontends.pi.transcript import PiTranscriptReader  # ruff: ignore[import-outside-top-level]

    return PiTranscriptReader()


def _skill_hint(skills: Sequence[str]) -> str:
    named = ", ".join(f"`{skill}` (`{_skills_dir() / skill / 'SKILL.md'}`)" for skill in skills)
    return (
        f"Skills that may fit this task: {named}. If one applies, read it before you start. Ignore any that don't fit."
    )


@frontend(
    name="pi",
    display_name="Pi",
    make_installer=_installer,
    detect_priority=EXACT_MATCH,
    skills_dir=_skills_dir,
    skill_hint=_skill_hint,
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
    envelope_model: ClassVar[type[PayloadEnvelope]] = deferred(_envelope_model)
    hook_models: ClassVar[Mapping[CanonicalHook, type[HookFields]]] = deferred(_hook_models)
    tool_models: ClassVar[Mapping[CanonicalTool, type[ToolParams]]] = deferred(_tool_models)
    transcript: ClassVar[TranscriptReader] = deferred(_transcript)
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

    def supports_user_message(self) -> bool:
        """Pi surfaces a user message through the bridge extension.

        Returns:
            True, since the bridge relays it to `ctx.ui.notify`.
        """
        return True

    def allow(self, message: str | None = None, *, system_message: str | None = None) -> NoReturn:
        """Allow via exit 0, context on stdout, or JSON when there is a user message."""
        if system_message is None:
            exit_allow(message)
        exit_allow(json.dumps({"message": message, "system_message": system_message}))

    def allow_with_input(
        self,
        updated_input: Mapping[str, Any],
        message: str | None = None,
        *,
        fallback_message: str | None = None,
        system_message: str | None = None,
    ) -> NoReturn:
        """Allow via exit 0, JSON on stdout that the bridge extension copies into the tool input."""
        exit_allow(json.dumps({"updated_input": dict(updated_input), "message": message}))

    def block(self, message: str) -> NoReturn:
        """Block via exit 2, error on stderr."""
        exit_block(message)
