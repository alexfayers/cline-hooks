"""Class attributes resolved on first access, so a module need not import what they hold until it is used."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Callable


class _Deferred[T]:
    """A class attribute whose value `factory` builds on first access and caches."""

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._value: T | None = None

    def __get__(self, instance: object, owner: type | None = None) -> T:
        """Return the cached value, building it first if need be.

        Returns:
            The value `factory` built.
        """
        if self._value is None:
            self._value = self._factory()
        return self._value


def deferred[T](factory: Callable[[], T]) -> T:
    """Declare a class attribute that `factory` builds on first access.

    Args:
        factory: Builds the value; imports it needs belong inside it.

    Returns:
        The descriptor, typed as the value it yields.
    """
    return cast("T", _Deferred(factory))
