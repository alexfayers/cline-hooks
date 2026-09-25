# ruff: file-ignore[print]
"""Antigravity JSON stdout protocol."""

from __future__ import annotations

from dataclasses import replace
import json
import sys
from typing import TYPE_CHECKING, Any, ClassVar, NoReturn, Self

from cline_hooks.core.frontend import EXACT_MATCH, frontend
from cline_hooks.core.outcome import Disposition
from cline_hooks.core.payload import (
    PayloadEnvelope,
    StandardPayloadProtocol,
    ToolParams,
    ensure_dict,
    parse_standard_payload,
)
from cline_hooks.core.protocol import HookRegistration
from cline_hooks.core.response import Response
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool
from cline_hooks.frontends.antigravity.install import AntigravityInstaller
from cline_hooks.frontends.antigravity.models import (
    AntigravityEditWriteParams,
    AntigravityEnvelope,
    AntigravityPostToolUse,
    AntigravityReadParams,
    AntigravityShellParams,
    AntigravityStop,
    AntigravityWebParams,
)
from cline_hooks.frontends.antigravity.transcript import AntigravityTranscriptReader

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cline_hooks.core.models import HookFields, HookInput
    from cline_hooks.core.outcome import Outcome
    from cline_hooks.core.protocol import RawPayload
    from cline_hooks.core.transcript import TranscriptReader

# Antigravity sends both on every event, and no other frontend sends either.
_ENVELOPE_KEYS = ("conversationId", "artifactDirectoryPath")

# Antigravity does not prefix an MCP call's tool name, so no native name marks
# one; a prefix no tool name can carry stops any from being read as one.
_NO_MCP_PREFIX = "\x00"

# The key parse() writes the inferred event under, since no payload names one.
_HOOK_EVENT_KEY = "hookEventName"


@frontend(
    name="antigravity",
    display_name="Antigravity",
    installer=AntigravityInstaller(),
    detect_priority=EXACT_MATCH,
)
class AntigravityProtocol(StandardPayloadProtocol):
    """Antigravity JSON stdout protocol.

    Each event answers on stdout with a decision and exits 0. A PostToolUse
    response is read as an empty object, so a note raised after a tool call
    cannot reach the model.
    """

    supported_hooks: ClassVar[Mapping[CanonicalHook, HookRegistration]] = {
        CanonicalHook.PRE_TOOL_USE: HookRegistration("PreToolUse", "*"),
        CanonicalHook.POST_TOOL_USE: HookRegistration("PostToolUse", "*"),
        CanonicalHook.STOP: HookRegistration("Stop"),
    }
    tool_map: ClassVar[Mapping[str, CanonicalTool]] = {
        "run_command": CanonicalTool.SHELL,
        "view_file": CanonicalTool.READ,
        "write_to_file": CanonicalTool.WRITE,
        "replace_file_content": CanonicalTool.EDIT,
        "multi_replace_file_content": CanonicalTool.EDIT,
        "read_url_content": CanonicalTool.WEB_FETCH,
        "search_web": CanonicalTool.WEB_SEARCH,
        "invoke_subagent": CanonicalTool.SPAWN_AGENT,
    }
    envelope_model: ClassVar[type[PayloadEnvelope]] = AntigravityEnvelope
    hook_models: ClassVar[Mapping[CanonicalHook, type[HookFields]]] = {
        CanonicalHook.POST_TOOL_USE: AntigravityPostToolUse,
        CanonicalHook.STOP: AntigravityStop,
    }
    tool_models: ClassVar[Mapping[CanonicalTool, type[ToolParams]]] = {
        CanonicalTool.SHELL: AntigravityShellParams,
        CanonicalTool.READ: AntigravityReadParams,
        CanonicalTool.EDIT: AntigravityEditWriteParams,
        CanonicalTool.WRITE: AntigravityEditWriteParams,
        CanonicalTool.WEB_FETCH: AntigravityWebParams,
        CanonicalTool.WEB_SEARCH: AntigravityWebParams,
    }
    transcript: ClassVar[TranscriptReader] = AntigravityTranscriptReader()
    mcp_prefix: ClassVar[str] = _NO_MCP_PREFIX
    mcp_separator: ClassVar[str] = _NO_MCP_PREFIX
    hook_event_key: ClassVar[str] = _HOOK_EVENT_KEY

    def __init__(self, hook: str = CanonicalHook.PRE_TOOL_USE) -> None:
        """Store the hook whose output contract this instance answers on.

        Args:
            hook: The canonical hook inferred from the incoming payload.
        """
        self._hook = hook

    @classmethod
    def detect(cls, payload: RawPayload) -> bool:
        """Detect Antigravity's hook JSON shape.

        Antigravity names no event, so detection reads its envelope instead.

        Returns:
            True if the payload carries Antigravity's own envelope keys.
        """
        data = payload.data
        if data is None:
            return False
        return all(key in data for key in _ENVELOPE_KEYS)

    @classmethod
    def infer_hook_event(cls, data: Mapping[str, Any]) -> str:
        """Return the hook a payload's own fields identify.

        Each event is recognised by a field only it carries: `fullyIdle` for
        Stop, and - the tool events being otherwise identical - `error` for
        PostToolUse, which only a call that has already run reports.

        Args:
            data: The raw payload data.

        Returns:
            The canonical hook name, or "" where the payload identifies none.
        """
        if "fullyIdle" in data:
            return CanonicalHook.STOP
        if "toolCall" not in data:
            return ""
        if "error" in data:
            return CanonicalHook.POST_TOOL_USE
        return CanonicalHook.PRE_TOOL_USE

    @classmethod
    def from_payload(cls, payload: RawPayload) -> Self:
        """Construct a protocol answering on the inferred event's contract.

        Returns:
            An AntigravityProtocol carrying the payload's inferred hook.
        """
        return cls(cls.infer_hook_event(payload.data or {}))

    def parse(self, payload: RawPayload) -> HookInput:
        """Parse the payload, naming its event and flattening its tool call.

        Returns:
            The most specific matching HookInput subclass.
        """
        data = payload.data or {}
        tool_call = ensure_dict(data.get("toolCall"))
        named = {
            **data,
            self.hook_event_key: self.infer_hook_event(data),
            "tool_name": tool_call.get("name", ""),
            "tool_input": tool_call.get("args", {}),
        }
        return parse_standard_payload(replace(payload, data=named), type(self))

    def _respond(self, decision: Mapping[str, str]) -> NoReturn:
        """Answer with one JSON decision on stdout and exit 0."""
        print(json.dumps(decision), end="")
        sys.exit(0)

    def allow(self, message: str | None = None, *, system_message: str | None = None) -> NoReturn:
        """Allow via JSON stdout, carrying any context as the decision's reason."""
        if self._hook == CanonicalHook.POST_TOOL_USE:
            self._respond({})
        decision = {"decision": "allow"}
        if message is not None:
            decision["reason"] = message
        self._respond(decision)

    def block(self, message: str) -> NoReturn:
        """Deny the tool call via JSON stdout, or re-enter a loop that stopped."""
        if self._hook == CanonicalHook.POST_TOOL_USE:
            self._respond({})
        if self._hook == CanonicalHook.STOP:
            self._respond({"decision": "continue", "reason": message})
        self._respond({"decision": "deny", "reason": message})

    def render(self, outcome: Outcome) -> Response:
        """Render the outcome as Antigravity's JSON stdout decision for this instance's hook.

        Returns:
            The rendered Response.
        """
        if self._hook == CanonicalHook.POST_TOOL_USE:
            return Response(stdout=json.dumps({}))
        if outcome.disposition in {Disposition.BLOCK, Disposition.FEEDBACK}:
            if self._hook == CanonicalHook.STOP:
                decision: dict[str, str] = {"decision": "continue", "reason": outcome.message or ""}
            else:
                decision = {"decision": "deny", "reason": outcome.message or ""}
            return Response(stdout=json.dumps(decision))
        message = outcome.message
        if message is not None and outcome.label:
            message = f"{outcome.label}: {message}"
        allow_decision: dict[str, str] = {"decision": "allow"}
        if message is not None:
            allow_decision["reason"] = message
        return Response(stdout=json.dumps(allow_decision))
