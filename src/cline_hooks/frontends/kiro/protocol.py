# ruff: noqa: T201
"""Kiro exit-code protocol."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, ClassVar, NoReturn

from cline_hooks.core.payload import StandardPayloadProtocol
from cline_hooks.core.protocol import HookRegistration
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool, Frontend
from cline_hooks.frontends.kiro.parser import _KIRO_TOOL_MAP

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cline_hooks.core.protocol import RawPayload


class KiroProtocol(StandardPayloadProtocol):
    """Kiro exit-code protocol: exit 0 + stdout for allow, exit 2 + stderr for block."""

    supported_hooks: ClassVar[Mapping[CanonicalHook, HookRegistration]] = {
        CanonicalHook.PRE_TOOL_USE: HookRegistration("preToolUse", "*"),
        CanonicalHook.POST_TOOL_USE: HookRegistration("postToolUse", "*"),
        CanonicalHook.TASK_START: HookRegistration("agentSpawn"),
        CanonicalHook.USER_PROMPT_SUBMIT: HookRegistration("userPromptSubmit"),
        CanonicalHook.STOP: HookRegistration("stop"),
    }
    frontends: ClassVar[tuple[Frontend, ...]] = (Frontend.KIRO,)
    tool_map: ClassVar[Mapping[str, CanonicalTool]] = _KIRO_TOOL_MAP
    mcp_prefix: ClassVar[str] = "@"
    mcp_separator: ClassVar[str] = "/"

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

    def allow(
        self, message: str | None = None, *, system_message: str | None = None
    ) -> NoReturn:  # noqa: ARG002
        """Allow via exit 0, context on stdout."""
        if message is not None:
            print(message, end="")
        sys.exit(0)

    def block(self, message: str) -> NoReturn:
        """Block via exit 2, error on stderr."""
        print(message, end="", file=sys.stderr)
        sys.exit(2)

    def feedback(self, message: str) -> NoReturn:
        """Continue via exit 0, Stop's decision JSON with message as reason.

        Kiro's `Stop` hook only surfaces feedback via this exit-0 JSON
        channel (see kiro.dev/docs/cli/hooks/#stop) - the default
        `Protocol.feedback()` (exit 2 + stderr) is a no-op here since `Stop`
        isn't attached to a tool call and can't be blocked.
        """
        print(json.dumps({"decision": "block", "reason": message}), end="")
        sys.exit(0)

    def research_trace_header(self) -> str:
        """Return the Stop research-trace header for Kiro.

        Unlike Claude Code, Kiro never surfaces this hook's raw output to the
        user - only the model's own reply is shown, appended directly after
        its prior turn text with no separator. So the instruction must tell
        the model to render the trace itself, on its own new line, as a bare
        citation with no narration - otherwise the model tends to explain or
        editorialize about the lookups instead of just listing them. An exact
        format string is spelled out because a looser instruction (e.g. "list
        tool + detail") still let the model invent its own punctuation, such
        as repeating a URL a second time in parentheses.
        """
        return (
            "RESEARCH TRACE: MUST start your reply with a line break, then write ONE "
            "line in exactly this format and nothing else: Sources: <tool> "
            '"<detail>", <tool> "<detail>", ... - substituting each tool/detail '
            "pair from the lookups below, copied verbatim, each detail written "
            "only once. No narration, no commentary, no parentheses, no restating "
            "a detail a second time."
        )
