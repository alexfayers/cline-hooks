"""Fingerprint over the resolved external-plugin set."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
from pathlib import Path
import time

_CACHE_SECONDS = 5.0
_cache: tuple[float, str] | None = None


def _source_files(top_level: str) -> list[Path]:
    try:
        spec = importlib.util.find_spec(top_level)
    except (ImportError, ValueError):
        return []
    if spec is None:
        return []
    if spec.submodule_search_locations:
        return [path for location in spec.submodule_search_locations for path in Path(location).rglob("*.py")]
    return [Path(spec.origin)] if spec.origin else []


def compute() -> str:
    """Hash the resolved `cline_hooks`-entry-point distributions plus their source-file mtimes.

    Returns:
        A hex digest that changes whenever an external `cline_hooks`
        entry-point distribution's version changes, or a source file of
        `cline_hooks` or an entry-point package changes mtime.
    """
    seen: set[str] = set()
    parts: list[str] = []
    top_levels = {"cline_hooks"}
    for entry_point in importlib.metadata.entry_points(group="cline_hooks"):
        top_levels.add(entry_point.module.partition(".")[0])
        dist = entry_point.dist
        if dist is None or dist.name in seen:
            continue
        seen.add(dist.name)
        parts.append(f"{dist.name}=={dist.version}")
    parts.sort()

    max_mtime = 0.0
    for top_level in top_levels:
        for path in _source_files(top_level):
            try:
                max_mtime = max(max_mtime, path.stat().st_mtime)
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
