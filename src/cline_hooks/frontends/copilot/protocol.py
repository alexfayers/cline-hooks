"""GitHub Copilot CLI protocol: detection, parsing, and exit-code output."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, NoReturn

from cline_hooks.core.frontend import EXACT_MATCH, frontend
from cline_hooks.core.models import HookFields
from cline_hooks.core.protocol import HookRegistration, exit_allow, exit_block
from cline_hooks.core.vocabulary import CanonicalHook
from cline_hooks.frontends.claude_code.protocol import ClaudeCodeHookSpec
from cline_hooks.frontends.copilot.install import CopilotInstaller
from cline_hooks.frontends.copilot.models import CopilotPreCompact

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cline_hooks.core.protocol import RawPayload


@frontend(
    name="copilot",
    display_name="GitHub Copilot",
    installer=CopilotInstaller(),
    detect_priority=EXACT_MATCH,
)
class CopilotProtocol(ClaudeCodeHookSpec):
    """GitHub Copilot CLI protocol.

    cline-hooks registers Copilot's hooks under PascalCase event names, and
    GitHub's hooks reference documents PascalCase payloads as "VS Code
    compatible input": the same snake_case shape as Claude Code
    (hook_event_name, session_id, tool_name, tool_input, cwd), with
    tool_name reported as the Claude tool name (`Bash`, not `bash`) via a
    documented runtime-tool mapping. Copilot therefore inherits Claude Code's
    payload spec and adds PreCompact - a real Copilot event Claude Code has no
    counterpart for - which also gives PreCompact the sha256(cwd) session-id
    fallback a hand-rolled branch would lack. Only the tool NAME mapping is
    documented; the field names inside tool_input are not, so a tool_input
    whose keys differ from Claude's normalises to empty parameters rather than
    wrong ones. Copilot's output-channel format is likewise undocumented, so
    allow/block keep the plain exit-code contract rather than guessing a JSON
    envelope, and no transcript format is documented either, so Claude Code's
    transcript reader is deliberately not inherited.
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
        """Return the native event names only Copilot fires, not its shape source.

        Returns:
            Copilot's native hook event names that Claude Code never emits.
        """
        return cls.native_hook_names() - ClaudeCodeHookSpec.native_hook_names()

    @classmethod
    def detect(cls, payload: RawPayload) -> bool:
        """Detect only the events Claude Code has no counterpart for.

        Copilot's PascalCase payloads are documented as matching Claude
        Code's shape, and Copilot CLI documents no hook-subprocess
        environment signal (its full env-var reference has no analogue of
        CLAUDECODE), so nothing marks an ordinary Copilot event as Copilot's.
        An event name Claude Code never emits does: PreCompact can only have
        come from Copilot, and claiming it is what gets its fields parsed
        rather than dropped. Every other event falls through to
        ClaudeCodeProtocol, which parses it correctly by design - the same
        arrangement CodexProtocol relies on.

        Returns:
            True only for an event that is Copilot's alone.
        """
        data = payload.data
        if data is None:
            return False
        return data.get(cls.hook_event_key) in cls.own_hook_names()

    def allow(
        self, message: str | None = None, *, system_message: str | None = None
    ) -> NoReturn:  # noqa: ARG002
        """Allow via exit 0, context on stdout (see class docstring)."""
        exit_allow(message)

    def block(self, message: str) -> NoReturn:
        """Block via exit 2, error on stderr (see class docstring)."""
        exit_block(message)
