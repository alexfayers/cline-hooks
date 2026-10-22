"""The frontend spec, and the `@frontend` decorator that declares one.

Imports no frontend, so a frontend module can import this one freely;
`cline_hooks.core.frontends` orders the registrations into a registry.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import pkgutil
from typing import TYPE_CHECKING, TypeVar

import cline_hooks.frontends

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from cline_hooks.core.install import Installer
    from cline_hooks.core.protocol import Protocol, RawPayload

_ProtocolT = TypeVar("_ProtocolT", bound="type[Protocol]")

# Detection ordering, highest first: a shape-sniff must run last, or it claims
# payloads belonging to a frontend with an exact signal.
EXACT_MATCH = 10
SHAPE_SNIFF = 0

FRONTEND_ENV_KEY = "CLINE_HOOKS_FRONTEND"


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
        skills_dir: Returns where this frontend's installed skills live, or None where unknown.
        max_context_chars: The most characters of hook context this frontend takes at session start, or None.
    """

    name: str
    display_name: str
    protocol: type[Protocol]
    installer: Installer | None = None
    detect_priority: int = SHAPE_SNIFF
    default: bool = False
    skills_dir: Callable[[], Path] | None = None
    max_context_chars: int | None = None

    def install(self, target: str | None = None, *, force: bool = False) -> None:
        """Run this frontend's install step.

        Args:
            target: The install subcommand's positional argument, if any.
            force: Whether to repoint existing entries even where their binary exists.

        Raises:
            RuntimeError: If the frontend has no install step.
        """
        if self.installer is None:
            msg = f"{self.name} has no install step"
            raise RuntimeError(msg)
        self.installer.install(self.protocol, target, force=force)


REGISTERED_FRONTENDS: dict[str, FrontendSpec] = {}


def frontend(  # ruff: ignore[too-many-arguments]
    *,
    name: str,
    display_name: str,
    installer: Installer | None = None,
    detect_priority: int = SHAPE_SNIFF,
    default: bool = False,
    skills_dir: Callable[[], Path] | None = None,
    max_context_chars: int | None = None,
) -> Callable[[_ProtocolT], _ProtocolT]:
    """Register the decorated Protocol class as a supported frontend.

    Args:
        name: CLI slug for `cline-hook install <name>`, and fixture file stem.
        display_name: Human-readable name, used in generated docs.
        installer: How to install it, or None where it has no install step.
        detect_priority: `EXACT_MATCH` where detection reads an exact signal,
            `SHAPE_SNIFF` where it guesses from a payload's shape.
        default: Whether this frontend handles payloads nothing detects.
        skills_dir: Returns where this frontend's installed skills live, or None where unknown.
        max_context_chars: The most characters of hook context this frontend takes at session start, or None.

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
            skills_dir=skills_dir,
            max_context_chars=max_context_chars,
        )
        existing = REGISTERED_FRONTENDS.get(name)
        if existing is not None and existing.protocol is not cls:
            msg = f"frontend {name!r} is already registered by {existing.protocol.__name__}"
            raise RuntimeError(msg)
        REGISTERED_FRONTENDS[name] = spec
        cls.frontend_spec = spec
        return cls

    return decorator


def select_protocol(payload: RawPayload) -> type[Protocol]:
    """Return the protocol of the frontend the environment names, else the one that detects this payload.

    Returns:
        The protocol, or the default frontend's where nothing claims the payload.
    """
    name = payload.env.get(FRONTEND_ENV_KEY, "")
    package = name.replace("-", "_")
    if package in {module.name for module in pkgutil.iter_modules(cline_hooks.frontends.__path__)}:
        importlib.import_module(f"cline_hooks.frontends.{package}")
        if name in REGISTERED_FRONTENDS:
            return REGISTERED_FRONTENDS[name].protocol
    from cline_hooks.core.frontends import DEFAULT_PROTOCOL, DETECTION_ORDER  # ruff: ignore[import-outside-top-level]

    return next((spec.protocol for spec in DETECTION_ORDER if spec.protocol.detect(payload)), DEFAULT_PROTOCOL)
