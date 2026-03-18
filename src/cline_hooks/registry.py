from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

HOOK_HANDLERS: dict[str, Callable[..., Any]] = {}


def hook_handler(hook_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a handler for the given hook name.

    Args:
        hook_name: The Cline hook name to register the handler for.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        HOOK_HANDLERS[hook_name] = fn
        return fn

    return decorator
