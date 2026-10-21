"""Claude Code exit-code protocol."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Self

from cline_hooks.core.frontend import SHAPE_SNIFF, backticked, frontend
from cline_hooks.core.models import SubagentStartFields
from cline_hooks.core.outcome import Disposition
from cline_hooks.core.payload import (
    PayloadEnvelope,
    StandardPayloadProtocol,
    ToolParams,
)
from cline_hooks.core.protocol import HookRegistration, with_guard
from cline_hooks.core.response import Response
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool
from cline_hooks.frontends.claude_code.install import ClaudeCodeInstaller
from cline_hooks.frontends.claude_code.models import (
    ClaudeCodeEditWriteParams,
    ClaudeCodePostToolUse,
    ClaudeCodeReadParams,
    ClaudeCodeShellParams,
    ClaudeCodeStop,
    ClaudeCodeTaskStart,
    ClaudeCodeUserPromptSubmit,
)
from cline_hooks.frontends.claude_code.transcript import ClaudeCodeTranscriptReader

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from cline_hooks.core.models import HookFields
    from cline_hooks.core.outcome import Outcome
    from cline_hooks.core.protocol import RawPayload
    from cline_hooks.core.transcript import TranscriptReader


class ClaudeCodeHookSpec(StandardPayloadProtocol):
    """Claude Code's hook payload spec: its event names, tool names, field shapes.

    Held apart from `ClaudeCodeProtocol` so Codex and GitHub Copilot can
    inherit the payload shape alone, not Claude Code's output channel,
    transcript format, or direct-to-user channel.
    """

    supported_hooks: ClassVar[Mapping[CanonicalHook, HookRegistration]] = {
        CanonicalHook.TASK_START: HookRegistration("SessionStart"),
        CanonicalHook.USER_PROMPT_SUBMIT: HookRegistration("UserPromptSubmit"),
        CanonicalHook.PRE_TOOL_USE: HookRegistration("PreToolUse", matcher=""),
        CanonicalHook.POST_TOOL_USE: HookRegistration("PostToolUse", matcher=""),
        CanonicalHook.STOP: HookRegistration("Stop"),
        CanonicalHook.SUBAGENT_START: HookRegistration("SubagentStart"),
        CanonicalHook.SUBAGENT_STOP: HookRegistration("SubagentStop"),
    }
    tool_map: ClassVar[Mapping[str, CanonicalTool]] = {
        "Bash": CanonicalTool.SHELL,
        "Read": CanonicalTool.READ,
        "Edit": CanonicalTool.EDIT,
        "MultiEdit": CanonicalTool.EDIT,
        "NotebookEdit": CanonicalTool.EDIT,
        "Write": CanonicalTool.WRITE,
        "Skill": CanonicalTool.SKILL,
        "Task": CanonicalTool.SPAWN_AGENT,
        "Agent": CanonicalTool.SPAWN_AGENT,
        "Workflow": CanonicalTool.SPAWN_AGENT,
        "ExitPlanMode": CanonicalTool.PLAN_EXIT,
        "WebFetch": CanonicalTool.WEB_FETCH,
        "WebSearch": CanonicalTool.WEB_SEARCH,
        "SendMessage": CanonicalTool.SEND_MESSAGE,
    }
    envelope_model: ClassVar[type[PayloadEnvelope]] = PayloadEnvelope
    hook_models: ClassVar[Mapping[CanonicalHook, type[HookFields]]] = {
        CanonicalHook.POST_TOOL_USE: ClaudeCodePostToolUse,
        CanonicalHook.TASK_START: ClaudeCodeTaskStart,
        CanonicalHook.USER_PROMPT_SUBMIT: ClaudeCodeUserPromptSubmit,
        CanonicalHook.STOP: ClaudeCodeStop,
        CanonicalHook.SUBAGENT_START: SubagentStartFields,
        CanonicalHook.SUBAGENT_STOP: ClaudeCodeStop,
    }
    tool_models: ClassVar[Mapping[CanonicalTool, type[ToolParams]]] = {
        CanonicalTool.READ: ClaudeCodeReadParams,
        CanonicalTool.EDIT: ClaudeCodeEditWriteParams,
        CanonicalTool.WRITE: ClaudeCodeEditWriteParams,
        CanonicalTool.SHELL: ClaudeCodeShellParams,
    }
    mcp_prefix: ClassVar[str] = "mcp__"
    mcp_separators: ClassVar[tuple[str, ...]] = ("__",)


def _skill_hint(skills: Sequence[str]) -> str:
    return (
        f"Skills that may fit this task: {backticked(skills)}. "
        "If one applies, load it with the Skill tool before you start. Ignore any that don't fit."
    )


@frontend(
    name="claude-code",
    display_name="Claude Code",
    installer=ClaudeCodeInstaller(),
    detect_priority=SHAPE_SNIFF,
    skills_dir=lambda: Path.home() / ".claude" / "skills",
    max_context_chars=10_000,
    skill_hint=_skill_hint,
)
class ClaudeCodeProtocol(ClaudeCodeHookSpec):
    """Claude Code exit-code protocol.

    allow/feedback context uses hookSpecificOutput.additionalContext (exit 0)
    instead of plain stdout or exit 2, since Claude Code only surfaces plain
    stdout to the model for UserPromptSubmit/UserPromptExpansion/SessionStart
    - every other event needs additionalContext to actually reach the model.
    """

    supported_hooks: ClassVar[Mapping[CanonicalHook, HookRegistration]] = with_guard(ClaudeCodeHookSpec.supported_hooks)
    transcript: ClassVar[TranscriptReader] = ClaudeCodeTranscriptReader()

    def __init__(self, hook_event_name: str = "Stop") -> None:
        """Store the raw Claude Code hook event name for context injection.

        Args:
            hook_event_name: The raw hook_event_name from the incoming
                payload (not the remapped internal hookName), so the
                emitted hookSpecificOutput.hookEventName is always a valid
                Claude Code event name.
        """
        self._hook_event_name = hook_event_name

    @classmethod
    def detect(cls, payload: RawPayload) -> bool:
        """Detect a Claude Code payload via env, falling back to shape-sniffing.

        Returns:
            True if CLAUDECODE=1 is set in the environment, or - for
            invocations where env isn't inherited - the hook_event_name is
            PascalCase (Claude Code's own casing; Kiro's is lowercase/
            camelCase, verified against every event each frontend registers).
        """
        if payload.env.get("CLAUDECODE") == "1":
            return True
        data = payload.data
        if not isinstance(data, dict):
            return False
        name = data.get(cls.hook_event_key)
        return isinstance(name, str) and name[:1].isupper()

    @classmethod
    def from_payload(cls, payload: RawPayload) -> Self:
        """Construct a ClaudeCodeProtocol carrying the payload's raw hook event name.

        Returns:
            A ClaudeCodeProtocol instance for context-injection responses.
        """
        hook_event_name = "Stop"
        if isinstance(payload.data, dict):
            hook_event_name = payload.data.get(cls.hook_event_key, "Stop")
        return cls(hook_event_name)

    def supports_user_message(self) -> bool:
        """Claude Code surfaces a top-level systemMessage directly to the user.

        Returns:
            True, since Claude Code has a direct-to-user channel.
        """
        return True

    def supports_updated_input(self) -> bool:
        """Return True, as Claude Code applies hookSpecificOutput.updatedInput to the tool call."""
        return True

    def _payload(
        self,
        message: str | None,
        system_message: str | None,
        updated_input: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if system_message is not None:
            payload["systemMessage"] = system_message
        specific: dict[str, Any] = {}
        if updated_input is not None:
            specific["updatedInput"] = dict(updated_input)
        if message is not None:
            specific["additionalContext"] = message
        if specific:
            payload["hookSpecificOutput"] = {"hookEventName": self._hook_event_name, **specific}
        return payload

    def render(self, outcome: Outcome) -> Response:
        """Render the outcome via Claude Code's hookSpecificOutput/systemMessage contract.

        Returns:
            The rendered Response.
        """
        if outcome.disposition is Disposition.BLOCK:
            return super().render(outcome)
        if outcome.disposition is Disposition.FEEDBACK:
            payload = self._payload(outcome.message or "", None, None)
        else:
            payload = self._payload(outcome.labelled_message, outcome.user_message or None, outcome.updated_input)
        return Response(stdout=json.dumps(payload) if payload else "")
