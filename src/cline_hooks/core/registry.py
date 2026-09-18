from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from cline_hooks.core.outcome import Outcome
    from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool

HOOK_HANDLERS: dict[str, Callable[..., Any]] = {}


def hook_handler(
    hook_name: CanonicalHook,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register a handler for the given hook name.

    Args:
        hook_name: The hook name to register the handler for.

    Returns:
        A decorator that registers the decorated function as the handler.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        HOOK_HANDLERS[hook_name] = fn
        return fn

    return decorator


TOOL_HANDLERS: dict[tuple[str, str], Callable[..., Outcome]] = {}


def tool_handler(
    hook_name: CanonicalHook, *tools: CanonicalTool
) -> Callable[[Callable[..., Outcome]], Callable[..., Outcome]]:
    """Register a per-tool handler for the given hook and canonical tools.

    Args:
        hook_name: The hook name the handler applies to.
        *tools: The canonical tools the handler applies to.

    Returns:
        A decorator that registers the decorated function as the handler.
    """

    def decorator(fn: Callable[..., Outcome]) -> Callable[..., Outcome]:
        for tool in tools:
            TOOL_HANDLERS[hook_name, tool] = fn
        return fn

    return decorator
