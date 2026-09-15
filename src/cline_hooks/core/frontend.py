"""The frontend spec, and the `@frontend` decorator that declares one.

Imports no frontend, so a frontend module can import this one freely;
`cline_hooks.core.frontends` orders the registrations into a registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from cline_hooks.core.install import Installer
    from cline_hooks.core.protocol import Protocol

_ProtocolT = TypeVar("_ProtocolT", bound="type[Protocol]")

# Detection ordering, highest first: a shape-sniff must run last, or it claims
# payloads belonging to a frontend with an exact signal.
EXACT_MATCH = 10
SHAPE_SNIFF = 0


@dataclass(frozen=True)
class FrontendSpec:
    """Everything cline-hooks needs to know about one supported frontend.

    Attributes:
        name: CLI slug for `cline-hook install <name>`, and fixture file stem.
        display_name: Human-readable name, used in generated docs.
        protocol: The frontend's Protocol class.
        installer: How to install it, or None where it has no install step.
        detect_priority: Higher runs earlier during detection.
        default: Whether this frontend handles payloads nothing detects.
    """

    name: str
    display_name: str
    protocol: type[Protocol]
    installer: Installer | None = None
    detect_priority: int = SHAPE_SNIFF
    default: bool = False

    def install(self, target: str | None = None) -> None:
        """Run this frontend's install step.

        Args:
            target: The install subcommand's positional argument, if any.

        Raises:
            RuntimeError: If the frontend has no install step.
        """
        if self.installer is None:
            msg = f"{self.name} has no install step"
            raise RuntimeError(msg)
        self.installer.install(self.protocol, target)


REGISTERED_FRONTENDS: dict[str, FrontendSpec] = {}


def frontend(
    *,
    name: str,
    display_name: str,
    installer: Installer | None = None,
    detect_priority: int = SHAPE_SNIFF,
    default: bool = False,
) -> Callable[[_ProtocolT], _ProtocolT]:
    """Register the decorated Protocol class as a supported frontend.

    Args:
        name: CLI slug for `cline-hook install <name>`, and fixture file stem.
        display_name: Human-readable name, used in generated docs.
        installer: How to install it, or None where it has no install step.
        detect_priority: `EXACT_MATCH` where detection reads an exact signal,
            `SHAPE_SNIFF` where it guesses from a payload's shape.
        default: Whether this frontend handles payloads nothing detects.

    Returns:
        A decorator that registers the decorated class and returns it unchanged.
    """

    def decorator(cls: _ProtocolT) -> _ProtocolT:
        spec = FrontendSpec(
            name=name,
            display_name=display_name,
            protocol=cls,
            installer=installer,
            detect_priority=detect_priority,
            default=default,
        )
        existing = REGISTERED_FRONTENDS.get(name)
        if existing is not None and existing.protocol is not cls:
            msg = (
                f"frontend {name!r} is already registered "
                f"by {existing.protocol.__name__}"
            )
            raise RuntimeError(msg)
        REGISTERED_FRONTENDS[name] = spec
        cls.frontend_spec = spec
        return cls

    return decorator
