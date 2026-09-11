"""What a frontend is: its spec, and the decorator that declares one.

A frontend declares itself by decorating its Protocol class with `@frontend`,
the same way handlers declare themselves with `@hook_handler`. Everything true
of the frontend as a whole - what to call it, how to install it, how eagerly it
claims a payload - lives in that one decorator call, right above the class it
describes.

`cline_hooks.core.frontends` turns those registrations into the ordered
registry the rest of the package uses. Nothing here imports a frontend, so a
frontend module can import this one freely.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from cline_hooks.core.install import Installer
    from cline_hooks.core.protocol import Protocol

_ProtocolT = TypeVar("_ProtocolT", bound="type[Protocol]")

# Detection ordering, highest first. A frontend matching an exact signal must
# run before one that shape-sniffs, or the sniff claims its payloads.
EXACT_MATCH = 10
SHAPE_SNIFF = 0


@dataclass(frozen=True)
class FrontendSpec:
    """Everything cline-hooks needs to know about one supported frontend.

    Attributes:
        name: CLI slug for `cline-hook install <name>`, and the frontend's
            fixture file stem.
        display_name: Human-readable name, used in generated docs.
        protocol: The frontend's Protocol class.
        installer: How `cline-hook install <name>` sets the frontend up, or
            None where the frontend has no install step.
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
            target: The install subcommand's positional argument, where the
                frontend declares one.

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
        name: CLI slug for `cline-hook install <name>`, and the frontend's
            fixture file stem.
        display_name: Human-readable name, used in generated docs.
        installer: How to install this frontend, or None where it has no
            install step.
        detect_priority: Higher runs earlier during detection; use
            `EXACT_MATCH` for a frontend recognised by an exact signal and
            `SHAPE_SNIFF` for one recognised by the shape of a payload.
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
