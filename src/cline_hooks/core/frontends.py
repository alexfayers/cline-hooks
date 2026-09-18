"""Which frontends exist: import every frontend package, then order what registered.

Nothing here names a frontend - adding one is adding a package under
`cline_hooks.frontends`.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

from cline_hooks.core.frontend import REGISTERED_FRONTENDS, FrontendSpec
import cline_hooks.frontends

if TYPE_CHECKING:
    from cline_hooks.core.protocol import Protocol, RawPayload


def _discover() -> tuple[FrontendSpec, ...]:
    """Import every frontend package and return what registered itself.

    Returns:
        Every registered spec, ordered by name for stability.
    """
    for module_info in pkgutil.iter_modules(cline_hooks.frontends.__path__):
        importlib.import_module(f"{cline_hooks.frontends.__name__}.{module_info.name}")
    return tuple(sorted(REGISTERED_FRONTENDS.values(), key=lambda spec: spec.name))


def _default_frontend() -> FrontendSpec:
    """Return the frontend that handles payloads nothing detects.

    Returns:
        The single spec declaring `default=True`.

    Raises:
        RuntimeError: If the frontends do not declare exactly one default.
    """
    defaults = [spec for spec in FRONTENDS if spec.default]
    if len(defaults) != 1:
        msg = f"expected exactly one default frontend, found {len(defaults)}"
        raise RuntimeError(msg)
    return defaults[0]


FRONTENDS: tuple[FrontendSpec, ...] = _discover()
FRONTENDS_BY_NAME: dict[str, FrontendSpec] = {spec.name: spec for spec in FRONTENDS}

DETECTION_ORDER: tuple[FrontendSpec, ...] = tuple(
    sorted(FRONTENDS, key=lambda spec: (-spec.detect_priority, spec.name))
)
DEFAULT_FRONTEND: FrontendSpec = _default_frontend()
DEFAULT_PROTOCOL: type[Protocol] = DEFAULT_FRONTEND.protocol


def select_protocol(payload: RawPayload) -> type[Protocol]:
    """Return the frontend protocol class that detects this payload, or the default.

    Args:
        payload: The raw hook invocation data.

    Returns:
        The first protocol in detection order to claim the payload, else the
        default frontend's protocol.
    """
    for spec in DETECTION_ORDER:
        if spec.protocol.detect(payload):
            return spec.protocol
    return DEFAULT_PROTOCOL
