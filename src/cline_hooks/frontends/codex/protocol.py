"""Codex hook protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

from cline_hooks.core.frontend import frontend
from cline_hooks.core.protocol import exit_allow, exit_block
from cline_hooks.frontends.claude_code.protocol import ClaudeCodeHookSpec
from cline_hooks.frontends.codex.install import CodexInstaller

if TYPE_CHECKING:
    from cline_hooks.core.protocol import RawPayload


@frontend(name="codex", display_name="Codex", installer=CodexInstaller())
class CodexProtocol(ClaudeCodeHookSpec):
    """Codex hook protocol.

    Codex reuses Claude Code's hook JSON shape and native tool names exactly,
    so it inherits that payload spec and nothing else: its output channel is
    the plain exit-code contract, and its transcript format is undocumented.
    Nothing distinguishes a Codex invocation from a real Claude Code one, so
    `detect()` is always False and Codex payloads fall through to
    `ClaudeCodeProtocol`, which parses them identically.
    """

    @classmethod
    def detect(cls, payload: RawPayload) -> bool:
        """Never detect - nothing distinguishes Codex from Claude Code.

        Returns:
            False, always.
        """
        return False

    def allow(self, message: str | None = None, *, system_message: str | None = None) -> NoReturn:
        """Allow via exit 0, context on stdout."""
        exit_allow(message)

    def block(self, message: str) -> NoReturn:
        """Block via exit 2, error on stderr."""
        exit_block(message)
