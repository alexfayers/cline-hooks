"""cline-hooks: AI coding assistant lifecycle hook integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["main"]


def __getattr__(name: str) -> Callable[[], NoReturn]:
    """Lazily resolve `main` so importing `cline_hooks` alone stays light.

    Eagerly importing `cline_hooks._main` here would pull in the full plugin
    ensemble and every frontend protocol (pydantic included) on ANY import
    under this package - including a thin, latency-sensitive leaf module that
    has no reason to load any of that.

    Returns:
        The real `main` entry point, imported on first access.

    Raises:
        AttributeError: For any name other than `main`.
    """
    if name == "main":
        from cline_hooks._main import main  # ruff: ignore[import-outside-top-level]

        return main
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
