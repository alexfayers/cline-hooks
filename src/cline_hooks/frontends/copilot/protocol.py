"""GitHub Copilot CLI protocol: detection, parsing, and exit-code output."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, NoReturn

from cline_hooks.core.payload import StandardPayloadProtocol
from cline_hooks.core.protocol import HookRegistration, exit_allow, exit_block
from cline_hooks.core.vocabulary import CanonicalHook, Frontend
from cline_hooks.frontends.claude_code.protocol import ClaudeCodeProtocol
import cline_hooks.frontends.copilot.parser  # noqa: F401

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cline_hooks.core.protocol import RawPayload
    from cline_hooks.core.vocabulary import CanonicalTool


class CopilotProtocol(StandardPayloadProtocol):
    """GitHub Copilot CLI protocol.

    cline-hooks registers Copilot's hooks under PascalCase event names, and
    GitHub's hooks reference documents PascalCase payloads as "VS Code
    compatible input": the same snake_case shape as Claude Code
    (hook_event_name, session_id, tool_name, tool_input, cwd), with
    tool_name reported as the Claude tool name (`Bash`, not `bash`) via a
    documented runtime-tool mapping. Copilot therefore declares its own
    spec derived from Claude Code's, adding PreCompact - a real Copilot
    event Claude Code has no counterpart for. This also gives PreCompact
    the sha256(cwd) session-id fallback the hand-rolled branch lacked. Only
    the tool NAME mapping is documented; the field names inside tool_input
    are not, so a tool_input whose keys differ from Claude's normalises to
    empty parameters rather than wrong ones. Copilot's output-channel
    format is likewise undocumented, so allow/block keep the plain
    exit-code contract rather than guessing a JSON envelope.
    """

    supported_hooks: ClassVar[Mapping[CanonicalHook, HookRegistration]] = {
        **ClaudeCodeProtocol.supported_hooks,
        CanonicalHook.PRE_COMPACT: HookRegistration("PreCompact"),
    }
    frontends: ClassVar[tuple[Frontend, ...]] = (Frontend.COPILOT, Frontend.CLAUDE_CODE)
    tool_map: ClassVar[Mapping[str, CanonicalTool]] = ClaudeCodeProtocol.tool_map
    mcp_prefix: ClassVar[str] = ClaudeCodeProtocol.mcp_prefix
    mcp_separator: ClassVar[str] = ClaudeCodeProtocol.mcp_separator

    @classmethod
    def detect(cls, payload: RawPayload) -> bool:  # noqa: ARG003
        """Never positively detect Copilot.

        Copilot's PascalCase payloads are documented as matching Claude
        Code's shape, and Copilot CLI documents no hook-subprocess
        environment signal (its full env-var reference has no analogue of
        CLAUDECODE), so nothing distinguishes a Copilot payload from a real
        Claude Code one. Returning False lets ClaudeCodeProtocol's
        shape-sniff claim them, which parses them correctly by design -
        the same arrangement CodexProtocol relies on.

        Returns:
            False, always.
        """
        return False

    def allow(
        self, message: str | None = None, *, system_message: str | None = None
    ) -> NoReturn:  # noqa: ARG002
        """Allow via exit 0, context on stdout (see class docstring)."""
        exit_allow(message)

    def block(self, message: str) -> NoReturn:
        """Block via exit 2, error on stderr (see class docstring)."""
        exit_block(message)
