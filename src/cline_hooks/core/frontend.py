"""The frontend spec, and the `@frontend` decorator that declares one.

Imports no frontend, so a frontend module can import this one freely;
`cline_hooks.core.frontends` orders the registrations into a registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from cline_hooks.core.install import Installer
    from cline_hooks.core.protocol import Protocol

_ProtocolT = TypeVar("_ProtocolT", bound="type[Protocol]")

# Detection ordering, highest first: a shape-sniff must run last, or it claims
# payloads belonging to a frontend with an exact signal.
EXACT_MATCH = 10
SHAPE_SNIFF = 0


def backticked(names: Sequence[str]) -> str:
    """Join names as comma-separated inline code.

    Args:
        names: The names to join.

    Returns:
        The names, each in backticks.
    """
    return ", ".join(f"`{name}`" for name in names)


def default_skill_hint(skills: Sequence[str]) -> str:
    """Word a skill suggestion as a note to the spawner, for frontends that cannot change a spawn.

    Args:
        skills: The names of the skills that may fit the subagent.

    Returns:
        The suggestion text.
    """
    return f"Skills that may fit this subagent: {backticked(skills)}. Consider naming them in its task."


@dataclass(frozen=True)
class FrontendSpec:
    """Everything cline-hooks needs to know about one supported frontend.

    Attributes:
        name: CLI slug for `cline-hook install <name>`, and fixture file stem.
        display_name: Human-readable name, used in generated docs.
        protocol: The frontend's Protocol class.
        make_installer: Builds how to install it, or None where it has no install step.
        detect_priority: Higher runs earlier during detection.
        default: Whether this frontend handles payloads nothing detects.
        skills_dir: Returns where this frontend's installed skills live, or None where unknown.
        max_context_chars: The most characters of hook context this frontend takes at session start, or None.
        skill_hint: Words a suggestion of skills for a subagent, in this frontend's own way of loading one.
    """

    name: str
    display_name: str
    protocol: type[Protocol]
    make_installer: Callable[[], Installer] | None = None
    detect_priority: int = SHAPE_SNIFF
    default: bool = False
    skills_dir: Callable[[], Path] | None = None
    max_context_chars: int | None = None
    skill_hint: Callable[[Sequence[str]], str] = default_skill_hint

    @cached_property
    def installer(self) -> Installer | None:
        """How to install this frontend, built on first use.

        Returns:
            The installer, or None where the frontend has no install step.
        """
        return self.make_installer() if self.make_installer is not None else None

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
    make_installer: Callable[[], Installer] | None = None,
    detect_priority: int = SHAPE_SNIFF,
    default: bool = False,
    skills_dir: Callable[[], Path] | None = None,
    max_context_chars: int | None = None,
    skill_hint: Callable[[Sequence[str]], str] = default_skill_hint,
) -> Callable[[_ProtocolT], _ProtocolT]:
    """Register the decorated Protocol class as a supported frontend.

    Args:
        name: CLI slug for `cline-hook install <name>`, and fixture file stem.
        display_name: Human-readable name, used in generated docs.
        make_installer: Builds how to install it, or None where it has no install step.
        detect_priority: `EXACT_MATCH` where detection reads an exact signal,
            `SHAPE_SNIFF` where it guesses from a payload's shape.
        default: Whether this frontend handles payloads nothing detects.
        skills_dir: Returns where this frontend's installed skills live, or None where unknown.
        max_context_chars: The most characters of hook context this frontend takes at session start, or None.
        skill_hint: Words a suggestion of skills for a subagent, in this frontend's own way of loading one.

    Returns:
        A decorator that registers the decorated class and returns it unchanged.
    """

    def decorator(cls: _ProtocolT) -> _ProtocolT:
        spec = FrontendSpec(
            name=name,
            display_name=display_name,
            protocol=cls,
            make_installer=make_installer,
            detect_priority=detect_priority,
            default=default,
            skills_dir=skills_dir,
            max_context_chars=max_context_chars,
            skill_hint=skill_hint,
        )
        existing = REGISTERED_FRONTENDS.get(name)
        if existing is not None and existing.protocol is not cls:
            msg = f"frontend {name!r} is already registered by {existing.protocol.__name__}"
            raise RuntimeError(msg)
        REGISTERED_FRONTENDS[name] = spec
        cls.frontend_spec = spec
        return cls

    return decorator
