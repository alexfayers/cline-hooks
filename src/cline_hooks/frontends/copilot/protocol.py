"""GitHub Copilot CLI protocol: detection, parsing, and exit-code output."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, NoReturn

from cline_hooks.core.frontend import EXACT_MATCH, frontend
from cline_hooks.core.outcome import Disposition
from cline_hooks.core.protocol import HookRegistration, exit_allow, exit_block
from cline_hooks.core.response import Response
from cline_hooks.core.vocabulary import CanonicalHook
from cline_hooks.frontends.claude_code.protocol import ClaudeCodeHookSpec
from cline_hooks.frontends.copilot.install import CopilotInstaller
from cline_hooks.frontends.copilot.models import CopilotPreCompact

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cline_hooks.core.models import HookFields
    from cline_hooks.core.outcome import Outcome
    from cline_hooks.core.protocol import RawPayload


@frontend(
    name="copilot",
    display_name="GitHub Copilot",
    installer=CopilotInstaller(),
    detect_priority=EXACT_MATCH,
)
class CopilotProtocol(ClaudeCodeHookSpec):
    """GitHub Copilot CLI protocol.

    GitHub documents Copilot's PascalCase payloads as "VS Code compatible
    input" - Claude Code's snake_case shape, with tool_name reported as the
    Claude tool name (`Bash`, not `bash`) - so Copilot inherits that payload
    spec and adds PreCompact, an event Claude Code has no counterpart for.

    Only the tool NAME mapping is documented, so a tool_input whose keys differ
    from Claude's normalises to empty parameters rather than wrong ones. The
    output-channel and transcript formats are undocumented too, so allow/block
    keep the plain exit-code contract and Claude Code's transcript reader is
    not inherited.
    """

    supported_hooks: ClassVar[Mapping[CanonicalHook, HookRegistration]] = {
        **ClaudeCodeHookSpec.supported_hooks,
        CanonicalHook.PRE_COMPACT: HookRegistration("PreCompact"),
    }
    hook_models: ClassVar[Mapping[CanonicalHook, type[HookFields]]] = {
        **ClaudeCodeHookSpec.hook_models,
        CanonicalHook.PRE_COMPACT: CopilotPreCompact,
    }

    @classmethod
    def own_hook_names(cls) -> frozenset[str]:
        """Return the native event names only Copilot fires.

        Returns:
            Copilot's native hook event names that Claude Code never emits.
        """
        return cls.native_hook_names() - ClaudeCodeHookSpec.native_hook_names()

    @classmethod
    def detect(cls, payload: RawPayload) -> bool:
        """Detect only the events Claude Code has no counterpart for.

        Copilot documents no environment signal (no analogue of CLAUDECODE),
        so nothing marks an ordinary Copilot event as Copilot's. An event name
        Claude Code never emits does, and claiming it is what gets its fields
        parsed rather than dropped; every other event falls through to
        ClaudeCodeProtocol, which parses it identically.

        Returns:
            True only for an event that is Copilot's alone.
        """
        data = payload.data
        if data is None:
            return False
        return data.get(cls.hook_event_key) in cls.own_hook_names()

    def allow(self, message: str | None = None, *, system_message: str | None = None) -> NoReturn:
        """Allow via exit 0, context on stdout (see class docstring)."""
        exit_allow(message)

    def block(self, message: str) -> NoReturn:
        """Block via exit 2, error on stderr (see class docstring)."""
        exit_block(message)

    def render(self, outcome: Outcome) -> Response:
        """Render the outcome via the plain exit-code contract (see class docstring).

        Returns:
            The rendered Response.
        """
        if outcome.disposition in {Disposition.BLOCK, Disposition.FEEDBACK}:
            return Response(exit_code=2, stderr=outcome.message or "")
        message = outcome.message
        if message is not None and outcome.label:
            message = f"{outcome.label}: {message}"
        return Response(stdout=message or "")
