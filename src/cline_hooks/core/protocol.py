from __future__ import annotations

from abc import ABC, abstractmethod
from typing import NoReturn

_active_protocol: Protocol | None = None


class Protocol(ABC):
    """Abstract output protocol for hook responses."""

    @abstractmethod
    def allow(self, message: str | None = None) -> NoReturn:
        """Allow the operation, optionally injecting context."""

    @abstractmethod
    def block(self, message: str) -> NoReturn:
        """Block the operation with an error message."""

    def feedback(self, message: str) -> NoReturn:
        """Continue the conversation with non-error feedback. Defaults to block()."""
        self.block(message)


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
