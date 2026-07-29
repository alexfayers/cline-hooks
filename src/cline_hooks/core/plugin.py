from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import importlib.metadata
import logging
import pkgutil
from typing import TYPE_CHECKING

import cline_hooks.plugins as _plugins_pkg

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from cline_hooks.handlers.commands import CommandRule

logger = logging.getLogger("hooks")


@dataclass
class HookResult:
    """Result from a plugin hook handler.

    Attributes:
        notes: Context strings to inject into the response.
        block: If set, block the tool call with this reason.
    """

    notes: list[str] = field(default_factory=list)
    block: str | None = None


@dataclass
class ToolingNote:
    """A plugin-supplied ecosystem tooling note.

    Attributes:
        note: The guidance text to show.
        replaces_generic: If True, suppress the generic ecosystem tooling
            note in favour of this one. If False, this note is shown
            alongside the generic note (or lack thereof).
    """

    note: str
    replaces_generic: bool = True


def collect_hook_results(plugins: list[HooksPlugin], hook_name: str, **kwargs: object) -> HookResult:
    """Collect and merge HookResults from all plugins for a given hook.

    Args:
        plugins: The loaded plugin instances.
        hook_name: The hook event name.
        **kwargs: Hook-specific keyword arguments passed to each plugin.

    Returns:
        A merged HookResult with all notes and the first block reason found.
    """
    merged = HookResult()
    for plugin in plugins:
        result = plugin.on_hook(hook_name, **kwargs)
        if result is None:
            continue
        merged.notes.extend(result.notes)
        if result.block and merged.block is None:
            merged.block = result.block
    return merged


class HooksPlugin:
    """Base class for hook plugins.

    Override any methods to provide custom behaviour. All methods return
    empty/None by default so the core framework has zero built-in opinions.
    """

    def get_build_commands(self) -> frozenset[str]:
        """Return command names that are considered build tools.

        Returns:
            frozenset of command name strings.
        """
        return frozenset()

    def get_command_rules(self) -> list[CommandRule]:
        """Return CommandRule instances this plugin wants to enforce.

        Returns:
            List of CommandRule objects.
        """
        return []

    def get_state_write_tool_names(self) -> frozenset[str]:
        """Return MCP tool names that are considered state-write operations.

        Returns:
            frozenset of tool name strings.
        """
        return frozenset()

    def get_research_tool_names(self) -> frozenset[str]:
        """Return additional tool names that count as research lookups.

        Returns:
            frozenset of tool name strings.
        """
        return frozenset()

    def get_research_detail_extractors(self) -> dict[str, Callable[[dict[str, Any]], str]]:
        """Return per-tool detail extractors for research lookups.

        Each maps a research tool name to a callable that derives a short
        detail string (e.g. a URL or query) from that tool's parameters.

        Returns:
            Mapping of tool name to a detail-extraction callable.
        """
        return {}

    def get_tooling_note(self, workspace_roots: list[str]) -> ToolingNote | None:  # noqa: ARG002
        """Return this plugin's ecosystem tooling note for these workspace roots.

        Overriding plugins use this to supply their own build-tool guidance,
        optionally replacing the generic ecosystem tooling note for the same
        roots (regardless of which ecosystem detector would otherwise have
        matched).

        Args:
            workspace_roots: List of workspace root paths.

        Returns:
            None by default.
        """
        return None

    def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:  # noqa: ARG002
        """Handle any hook event, returning notes and/or a block reason.

        Args:
            hook_name: The hook event name (e.g. "TaskStart", "PreToolUse").
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult with notes/block, or None to do nothing.
        """
        return None


class _PluginCache:
    """Holds the cached list of loaded plugins for the process lifetime."""

    def __init__(self) -> None:
        self._loaded: list[HooksPlugin] | None = None

    def get(self) -> list[HooksPlugin] | None:
        """Return the cached plugin list, or None if not yet loaded."""
        return self._loaded

    def set(self, plugins: list[HooksPlugin]) -> None:
        """Store the loaded plugin list in the cache."""
        self._loaded = plugins


_plugin_cache = _PluginCache()


def load_plugins() -> list[HooksPlugin]:
    """Load all plugins: bundled from cline_hooks.plugins, then external entry points.

    Results are cached for the lifetime of the process.

    Returns:
        List of loaded HooksPlugin instances.
    """
    cached = _plugin_cache.get()
    if cached is not None:
        return cached

    loaded: list[HooksPlugin] = []

    for _finder, name, _ispkg in pkgutil.iter_modules(_plugins_pkg.__path__, _plugins_pkg.__name__ + "."):
        try:
            module = importlib.import_module(name)
            for attr in vars(module).values():
                if isinstance(attr, type) and issubclass(attr, HooksPlugin) and attr is not HooksPlugin:
                    loaded.append(attr())
                    logger.debug("Loaded bundled plugin: %s", attr.__name__)
        except Exception:
            logger.exception("Failed to load bundled plugin module: %s", name)

    for ep in importlib.metadata.entry_points(group="cline_hooks"):
        try:
            cls = ep.load()
            if isinstance(cls, type) and issubclass(cls, HooksPlugin):
                loaded.append(cls())
                logger.debug("Loaded external plugin: %s", ep.name)
        except Exception:
            logger.exception("Failed to load external plugin: %s", ep.name)

    _plugin_cache.set(loaded)
    return loaded


# Deprecated alias for backward compatibility with external plugins.
ClineHooksPlugin = HooksPlugin
