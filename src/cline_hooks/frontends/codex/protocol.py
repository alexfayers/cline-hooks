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

    Codex reuses Claude Code's hook JSON shape and native tool names
    (Bash/Edit/Write/Read/Skill) exactly, so it inherits Claude Code's payload
    spec wholesale. It inherits nothing else: Codex's output channel is the
    plain exit-code contract, and its transcript format is undocumented, so it
    keeps the default "no readable transcript" rather than guessing at Claude
    Code's JSONL. No env var or payload signal was found that distinguishes a
    genuine Codex invocation from a real Claude Code one, so `detect()`
    returns False unconditionally - Codex payloads fall through to
    `ClaudeCodeProtocol`, which parses them correctly anyway since the shape
    is identical.
    """

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
