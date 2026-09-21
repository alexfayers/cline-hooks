"""Fingerprint over the resolved external-plugin set, so a daemon can detect it's stale.

Load-bearing: external plugin packages (e.g. mcp-memory's MemoryPlugin,
FayersClineHooks' AmazonPlugin) upgrade independently of `cline-hook install`
ever running. A long-lived daemon would otherwise serve a stale plugin set
indefinitely after such an upgrade, with no symptom except wrong behaviour.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path
import sys
import time

_CACHE_SECONDS = 5.0
_cache: tuple[float, str] | None = None


def compute() -> str:
    """Hash the resolved `cline_hooks`-entry-point distributions plus loaded module mtimes.

    Returns:
        A hex digest that changes whenever an external `cline_hooks`
        entry-point distribution's version changes, or a loaded
        `cline_hooks` module file's mtime changes.
    """
    seen: set[str] = set()
    parts: list[str] = []
    for entry_point in importlib.metadata.entry_points(group="cline_hooks"):
        dist = entry_point.dist
        if dist is None or dist.name in seen:
            continue
        seen.add(dist.name)
        parts.append(f"{dist.name}=={dist.version}")
    parts.sort()

    max_mtime = 0.0
    for name, module in list(sys.modules.items()):
        if name != "cline_hooks" and not name.startswith("cline_hooks."):
            continue
        path = getattr(module, "__file__", None)
        if not path:
            continue
        try:
            max_mtime = max(max_mtime, Path(path).stat().st_mtime)
        except OSError:
            continue
    parts.append(f"mtime={max_mtime}")

    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def cached() -> str:
    """Return `compute()`'s result, recomputed at most once every 5 seconds.

    Returns:
        The cached or freshly computed fingerprint.
    """
    global _cache  # ruff: ignore[global-statement]
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < _CACHE_SECONDS:
        return _cache[1]
    value = compute()
    _cache = (now, value)
    return value
