from __future__ import annotations

import importlib
import importlib.metadata
import logging
import pkgutil
from typing import TYPE_CHECKING

import cline_hooks.plugins as _plugins_pkg

if TYPE_CHECKING:
    from cline_hooks.handlers.commands import CommandRule

logger = logging.getLogger("hooks")


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

    def get_workspace_context(self, workspace_roots: list[str]) -> str | None:  # noqa: ARG002
        """Return a context string to inject on TaskStart, or None.

        Args:
            workspace_roots: The workspace root paths for the current task.

        Returns:
            A context string, or None if this plugin has nothing to add.
        """
        return None

    def validate_tool(
        self,
        task_id: str,  # noqa: ARG002
        tool_name: str,  # noqa: ARG002
        parameters: dict[str, object],  # noqa: ARG002
    ) -> str | None:
        """Validate any tool call, returning a block message or None.

        Args:
            task_id: The session or task identifier.
            tool_name: The canonical tool name being called.
            parameters: The tool parameters.

        Returns:
            A block reason string if the call should be blocked, else None.
        """
        return None

    def validate_mcp_tool(
        self,
        task_id: str,  # noqa: ARG002
        tool_name: str,  # noqa: ARG002
        arguments: dict[str, object],  # noqa: ARG002
    ) -> str | None:
        """Validate an MCP tool call, returning a block message or None.

        Args:
            task_id: The session or task identifier.
            tool_name: The inner MCP tool name being called.
            arguments: The tool arguments.

        Returns:
            A block reason string if the call should be blocked, else None.
        """
        return None

    def on_post_tool_use(
        self,
        task_id: str,  # noqa: ARG002
        tool_name: str,  # noqa: ARG002
        is_memory_write: bool,  # noqa: ARG002
    ) -> str | None:
        """Called after every tool use. Return a note string to emit, or None.

        Args:
            task_id: The session or task identifier.
            tool_name: The tool that was just used.
            is_memory_write: Whether the tool call was a memory write operation.

        Returns:
            A note string to emit via allow(), or None.
        """
        return None

    def on_task_start(self, task_id: str) -> None:
        """Called when a new task starts.

        Args:
            task_id: The session or task identifier.
        """

    def on_task_end(self, task_id: str) -> None:
        """Called when a task ends (complete or cancel).

        Args:
            task_id: The session or task identifier.
        """


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
