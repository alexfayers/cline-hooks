from __future__ import annotations

from abc import ABC, abstractmethod
from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import cache
import json
import os
from typing import TYPE_CHECKING, Any, ClassVar, Self

from cline_hooks.core.outcome import Disposition
from cline_hooks.core.response import Response
from cline_hooks.core.transcript import NULL_TRANSCRIPT, TranscriptReader
from cline_hooks.core.vocabulary import CanonicalHook

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cline_hooks.core.frontend import FrontendSpec
    from cline_hooks.core.models import HookInput
    from cline_hooks.core.outcome import Outcome
    from cline_hooks.core.vocabulary import CanonicalTool

_active_protocol: ContextVar[Protocol | None] = ContextVar("_active_protocol", default=None)


@dataclass(frozen=True)
class RawPayload:
    """Raw hook invocation data, before any frontend-specific parsing."""

    raw: str
    data: dict[str, Any] | None
    env: Mapping[str, str]

    @classmethod
    def from_stdin(cls, raw: str) -> RawPayload:
        """Build a RawPayload from the raw stdin string and the process environment.

        Args:
            raw: The raw JSON string read from stdin.

        Returns:
            A RawPayload with `data` set to the parsed JSON dict, or None if
            the raw input isn't valid JSON or isn't a JSON object.
        """
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            parsed = None
        data = parsed if isinstance(parsed, dict) else None
        return cls(raw=raw, data=data, env=os.environ)


@dataclass(frozen=True)
class HookRegistration:
    """A frontend's native name (and optional matcher) for a canonical hook."""

    native_name: str
    matcher: str | None = None
    binary_name: str | None = None


GUARD_BINARY = "cline-hook-guard"

GUARD_HOOKS = frozenset({
    CanonicalHook.USER_PROMPT_SUBMIT,
    CanonicalHook.PRE_TOOL_USE,
    CanonicalHook.POST_TOOL_USE,
    CanonicalHook.STOP,
})


def with_guard(registrations: Mapping[CanonicalHook, HookRegistration]) -> dict[CanonicalHook, HookRegistration]:
    """Return `registrations` with the relayed hooks routed through the guard binary."""
    return {
        hook: replace(registration, binary_name=GUARD_BINARY) if hook in GUARD_HOOKS else registration
        for hook, registration in registrations.items()
    }


class Protocol(ABC):
    """Abstract per-frontend detection, parsing, and output protocol."""

    supported_hooks: ClassVar[Mapping[CanonicalHook, HookRegistration]] = {}
    tool_map: ClassVar[Mapping[str, CanonicalTool]] = {}
    transcript: ClassVar[TranscriptReader] = NULL_TRANSCRIPT
    # Set by @frontend; None on a spec class that only carries a payload shape.
    frontend_spec: ClassVar[FrontendSpec | None] = None

    @classmethod
    def canonical_hook(cls, native_name: str) -> CanonicalHook | str:
        """Return the canonical hook for a native hook event name.

        Returns:
            The matching CanonicalHook, or the native name unchanged if this
            frontend registers no hook under it.
        """
        return _native_to_canonical(cls).get(native_name, native_name)

    @classmethod
    def uses_guard(cls) -> bool:
        """Return True if any of this frontend's hooks run through the guard binary."""
        return any(registration.binary_name for registration in cls.supported_hooks.values())

    @classmethod
    def fires(cls, canonical_hook: str) -> bool:
        """Whether this frontend fires the given canonical hook.

        A payload can carry an event name this frontend does not register, and
        such an event is not this frontend's to handle.

        Args:
            canonical_hook: The canonical hook name resolved from the payload.

        Returns:
            True if this frontend registers that hook.
        """
        return canonical_hook in cls.supported_hooks

    @classmethod
    def native_hook_names(cls) -> frozenset[str]:
        """Return every native hook event name this frontend registers.

        Returns:
            The frontend's native hook event names.
        """
        return frozenset(_native_to_canonical(cls))

    @classmethod
    def native_tool_name(cls, tool: CanonicalTool) -> str:
        """Return this frontend's own name for a canonical tool.

        Lets shared handler text name a tool the way the model calling it does.

        Args:
            tool: The canonical tool to name.

        Returns:
            The first native name mapped onto `tool`, or the canonical name
            where the frontend has none of its own.
        """
        for native_name, canonical in cls.tool_map.items():
            if canonical == tool:
                return native_name
        return tool.value

    @classmethod
    @abstractmethod
    def detect(cls, payload: RawPayload) -> bool:
        """Return True if this protocol's frontend produced the given payload."""

    @classmethod
    def from_payload(cls, payload: RawPayload) -> Self:
        """Construct an instance of this protocol from the detected payload.

        Returns:
            A default-constructed instance; overridden by protocols that need
            state captured from the payload (e.g. the raw hook event name).
        """
        return cls()

    @abstractmethod
    def parse(self, payload: RawPayload) -> HookInput:
        """Parse the raw payload into a typed HookInput."""

    def configure_logging(self) -> None:  # ruff: ignore[empty-method-without-abstract-decorator]
        """Adjust logging for this frontend. Defaults to a no-op."""

    def supports_user_message(self) -> bool:
        """Whether this protocol can surface a message directly to the user.

        Returns:
            False by default; overridden by protocols with a user channel.
        """
        return False

    def supports_updated_input(self) -> bool:
        """Whether this protocol can change a tool call's input.

        Returns:
            False by default; overridden by protocols that apply `Outcome.updated_input`.
        """
        return False

    def render(self, outcome: Outcome) -> Response:
        """Render an Outcome into a transport-agnostic Response, via the plain exit-code contract.

        Returns:
            Exit 2 with the message on stderr to block or give feedback, otherwise the message on stdout.
        """
        if outcome.disposition in {Disposition.BLOCK, Disposition.FEEDBACK}:
            return Response(exit_code=2, stderr=outcome.message or "")
        return Response(stdout=outcome.labelled_message or "")


@cache
def _native_to_canonical(protocol_cls: type[Protocol]) -> Mapping[str, CanonicalHook]:
    """Return the native-name -> CanonicalHook inversion of a protocol's hooks.

    Returns:
        A mapping from each native hook event name to its canonical hook.
    """
    return {registration.native_name: canonical for canonical, registration in protocol_cls.supported_hooks.items()}


def set_protocol(protocol: Protocol) -> None:
    """Set the active output protocol for this invocation."""
    _active_protocol.set(protocol)


def get_protocol() -> Protocol:
    """Return the active output protocol.

    Raises:
        RuntimeError: If no protocol has been set.
    """
    protocol = _active_protocol.get()
    if protocol is None:
        msg = "No protocol set. Call set_protocol() before processing hooks."
        raise RuntimeError(msg)
    return protocol
