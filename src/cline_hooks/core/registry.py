from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable

    from cline_hooks.core.models import HookInput
    from cline_hooks.core.outcome import Outcome
    from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool

_HookInputT = TypeVar("_HookInputT", bound="HookInput")

HOOK_HANDLERS: dict[str, Callable[[HookInput], Outcome | None]] = {}


def hook_handler(
    hook_name: CanonicalHook,
) -> Callable[[Callable[[_HookInputT], Outcome | None]], Callable[[_HookInputT], Outcome | None]]:
    """Register a handler for the given hook name.

    Each handler narrows its parameter to the specific HookInput subclass its
    hook always parses to; storage keeps the base-class signature since
    dispatch always looks a handler up by the matching hook name.

    Args:
        hook_name: The hook name to register the handler for.

    Returns:
        A decorator that registers the decorated function as the handler.
    """

    def decorator(fn: Callable[[_HookInputT], Outcome | None]) -> Callable[[_HookInputT], Outcome | None]:
        HOOK_HANDLERS[hook_name] = cast("Callable[[HookInput], Outcome | None]", fn)
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
