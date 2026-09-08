"""Codex hook protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, NoReturn

from cline_hooks.core.payload import StandardPayloadProtocol
from cline_hooks.core.protocol import HookRegistration, exit_allow, exit_block
from cline_hooks.core.vocabulary import Frontend
from cline_hooks.frontends.claude_code.protocol import ClaudeCodeProtocol

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cline_hooks.core.protocol import RawPayload
    from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool


class CodexProtocol(StandardPayloadProtocol):
    """Codex hook protocol.

    Codex reuses Claude Code's hook JSON shape and native tool names
    (Bash/Edit/Write/Read/Skill) exactly, so parsing reuses Claude Code's
    payload spec directly and hook-support metadata delegates to
    `ClaudeCodeProtocol`. No env var or payload signal was found that
    distinguishes a genuine Codex invocation from a real Claude Code one,
    so `detect()` returns False unconditionally - Codex payloads fall
    through to `ClaudeCodeProtocol`, which parses them correctly anyway
    since the shape is identical.
    """

    supported_hooks: ClassVar[Mapping[CanonicalHook, HookRegistration]] = (
        ClaudeCodeProtocol.supported_hooks
    )
    frontends: ClassVar[tuple[Frontend, ...]] = (Frontend.CLAUDE_CODE,)
    tool_map: ClassVar[Mapping[str, CanonicalTool]] = ClaudeCodeProtocol.tool_map
    mcp_prefix: ClassVar[str] = ClaudeCodeProtocol.mcp_prefix
    mcp_separator: ClassVar[str] = ClaudeCodeProtocol.mcp_separator

    @classmethod
    def detect(cls, payload: RawPayload) -> bool:
        """Never detect - no signal distinguishes Codex from Claude Code (see class docstring)."""
        return False

    def allow(
        self, message: str | None = None, *, system_message: str | None = None
    ) -> NoReturn:  # noqa: ARG002
        """Allow via exit 0, context on stdout."""
        exit_allow(message)

    def block(self, message: str) -> NoReturn:
        """Block via exit 2, error on stderr."""
        exit_block(message)
