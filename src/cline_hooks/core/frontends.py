"""Which frontends exist: import frontend packages on demand, then order what registered.

Nothing here names a frontend - adding one is adding a package under
`cline_hooks.frontends`. A caller that names its frontend in `CLINE_HOOKS_FRONTEND`
gets only that package imported. The registry names (`FRONTENDS` and the rest)
import every frontend on first access.
"""

from __future__ import annotations

from functools import cache
import importlib
import pkgutil
from typing import TYPE_CHECKING, Any

from cline_hooks.core.frontend import REGISTERED_FRONTENDS, FrontendSpec
import cline_hooks.frontends

if TYPE_CHECKING:
    from cline_hooks.core.protocol import Protocol, RawPayload

    FRONTENDS: tuple[FrontendSpec, ...]
    FRONTENDS_BY_NAME: dict[str, FrontendSpec]
    DETECTION_ORDER: tuple[FrontendSpec, ...]
    DEFAULT_FRONTEND: FrontendSpec
    DEFAULT_PROTOCOL: type[Protocol]

FRONTEND_ENV_KEY = "CLINE_HOOKS_FRONTEND"


def _package_names() -> frozenset[str]:
    """Return the name of every frontend package, without importing any.

    Returns:
        The package names under `cline_hooks.frontends`.
    """
    return frozenset(module_info.name for module_info in pkgutil.iter_modules(cline_hooks.frontends.__path__))


def _import_frontend(package: str) -> None:
    """Import a frontend's protocol module, which registers its spec."""
    importlib.import_module(f"{cline_hooks.frontends.__name__}.{package}.protocol")


def _named_spec(name: str | None) -> FrontendSpec | None:
    """Import only the frontend a caller named.

    Args:
        name: The frontend's CLI slug, or None where the caller named none.

    Returns:
        The named frontend's spec, or None where the name is unset or unknown.
    """
    package = (name or "").replace("-", "_")
    if package not in _package_names():
        return None
    _import_frontend(package)
    return REGISTERED_FRONTENDS.get(name or "")


@cache
def _all_specs() -> tuple[FrontendSpec, ...]:
    """Import every frontend package and return what registered itself.

    Returns:
        Every registered spec, ordered by name for stability.
    """
    for package in _package_names():
        _import_frontend(package)
    return tuple(sorted(REGISTERED_FRONTENDS.values(), key=lambda spec: spec.name))


@cache
def _detection_order() -> tuple[FrontendSpec, ...]:
    """Order every frontend by the sequence detection tries them.

    Returns:
        Every spec, highest detect priority first, then by name.
    """
    return tuple(sorted(_all_specs(), key=lambda spec: (-spec.detect_priority, spec.name)))


@cache
def _default_frontend() -> FrontendSpec:
    """Return the frontend that handles payloads nothing detects.

    Returns:
        The single spec declaring `default=True`.

    Raises:
        RuntimeError: If the frontends do not declare exactly one default.
    """
    defaults = [spec for spec in _all_specs() if spec.default]
    if len(defaults) != 1:
        msg = f"expected exactly one default frontend, found {len(defaults)}"
        raise RuntimeError(msg)
    return defaults[0]


def __getattr__(name: str) -> Any:  # ruff: ignore[any-type]
    """Resolve the registry names, importing every frontend on first access.

    Returns:
        The named registry value.

    Raises:
        AttributeError: If `name` is not a registry name.
    """
    if name == "FRONTENDS":
        return _all_specs()
    if name == "FRONTENDS_BY_NAME":
        return {spec.name: spec for spec in _all_specs()}
    if name == "DETECTION_ORDER":
        return _detection_order()
    if name == "DEFAULT_FRONTEND":
        return _default_frontend()
    if name == "DEFAULT_PROTOCOL":
        return _default_frontend().protocol
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def select_protocol(payload: RawPayload) -> type[Protocol]:
    """Return the frontend protocol class that handles this payload.

    Args:
        payload: The raw hook invocation data.

    Returns:
        The protocol of the frontend the caller named, else the first protocol
        in detection order to claim the payload, else the default frontend's.
    """
    named = _named_spec(payload.env.get(FRONTEND_ENV_KEY))
    if named is not None:
        return named.protocol
    for spec in _detection_order():
        if spec.protocol.detect(payload):
            return spec.protocol
    return _default_frontend().protocol
