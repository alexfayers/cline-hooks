from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import cache
import json
import os
import sys
from typing import TYPE_CHECKING, Any, ClassVar, NoReturn, Self

from cline_hooks.core.transcript import NULL_TRANSCRIPT, TranscriptReader

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cline_hooks.core.frontend import FrontendSpec
    from cline_hooks.core.models import HookInput
    from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool

_active_protocol: Protocol | None = None


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


class Protocol(ABC):
    """Abstract per-frontend detection, parsing, and output protocol."""

    supported_hooks: ClassVar[Mapping[CanonicalHook, HookRegistration]] = {}
    tool_map: ClassVar[Mapping[str, CanonicalTool]] = {}
    transcript: ClassVar[TranscriptReader] = NULL_TRANSCRIPT
    # Set by @frontend on the class it decorates; None on a spec class that
    # only carries a payload shape for other frontends to inherit.
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
    def fires(cls, canonical_hook: str) -> bool:
        """Whether this frontend fires the given canonical hook.

        A payload can carry an event name this frontend does not register -
        a native name that happens to read like a canonical hook, or an event
        belonging to a frontend whose payloads are indistinguishable from this
        one's. Such an event is not this frontend's to handle.

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

        Lets shared handler text name a tool the way the model calling it
        does, without any handler knowing which frontend it is talking to.

        Args:
            tool: The canonical tool to name.

        Returns:
            The first native name this frontend maps onto `tool`, or the
            canonical name itself where the frontend has no name of its own.
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
    def from_payload(cls, payload: RawPayload) -> Self:  # noqa: ARG003
        """Construct an instance of this protocol from the detected payload.

        Returns:
            A default-constructed instance; overridden by protocols that need
            state captured from the payload (e.g. the raw hook event name).
        """
        return cls()

    @abstractmethod
    def parse(self, payload: RawPayload) -> HookInput:
        """Parse the raw payload into a typed HookInput."""

    def configure_logging(self) -> None:
        """Adjust logging for this frontend. Defaults to a no-op."""

    @abstractmethod
    def allow(
        self, message: str | None = None, *, system_message: str | None = None
    ) -> NoReturn:
        """Allow the operation, optionally injecting context."""

    def supports_user_message(self) -> bool:
        """Whether this protocol can surface a message directly to the user.

        Returns:
            False by default; overridden by protocols with a user channel.
        """
        return False

    @abstractmethod
    def block(self, message: str) -> NoReturn:
        """Block the operation with an error message."""

    def feedback(self, message: str) -> NoReturn:
        """Continue the conversation with non-error feedback. Defaults to block()."""
        self.block(message)

    def research_trace_header(self) -> str:
        """Return the instruction header prepended to a Stop research trace.

        The default makes no assumption about where a hook's output surfaces,
        so it asks the model to cite the lookups itself. Frontends that show
        this hook's raw output to the user, or that need an exact rendering
        format, override it.

        Returns:
            The instruction header for this frontend.
        """
        return (
            "RESEARCH TRACE: MUST cite the lookups behind this turn's claims to "
            "the user, in ONE line only."
        )


@cache
def _native_to_canonical(protocol_cls: type[Protocol]) -> Mapping[str, CanonicalHook]:
    """Return the native-name -> CanonicalHook inversion of a protocol's hooks.

    Returns:
        A mapping from each native hook event name to its canonical hook.
    """
    return {
        registration.native_name: canonical
        for canonical, registration in protocol_cls.supported_hooks.items()
    }


def exit_allow(message: str | None = None) -> NoReturn:
    """Allow via exit 0, context on stdout."""
    if message is not None:
        print(message, end="")  # noqa: T201
    sys.exit(0)


def exit_block(message: str) -> NoReturn:
    """Block via exit 2, error on stderr."""
    print(message, end="", file=sys.stderr)  # noqa: T201
    sys.exit(2)


def set_protocol(protocol: Protocol) -> None:
    """Set the active output protocol for this process."""
    global _active_protocol  # noqa: PLW0603
    _active_protocol = protocol


def get_protocol() -> Protocol:
    """Return the active output protocol.

    Raises:
        RuntimeError: If no protocol has been set.
    """
    if _active_protocol is None:
        msg = "No protocol set. Call set_protocol() before processing hooks."
        raise RuntimeError(msg)
    return _active_protocol
