from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import importlib.metadata
import inspect
import logging
import pkgutil
from typing import TYPE_CHECKING

import cline_hooks.plugins as _plugins_pkg

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from cline_hooks.handlers.commands import CommandRule

logger = logging.getLogger("hooks.plugin_loader")


@dataclass
class UserFacingNote:
    """A note destined for the user rather than the model.

    Attributes:
        user_text: Human-readable copy, free of model-directive text, shown
            directly to the user on frontends that support a user channel.
    """

    user_text: str


@dataclass
class HookResult:
    """Result from a plugin hook handler.

    Attributes:
        notes: Context strings to inject into the response.
        block: If set, block the tool call with this reason.
        user_notes: Notes destined for the user rather than the model.
    """

    notes: list[str] = field(default_factory=list)
    block: str | None = None
    user_notes: list[UserFacingNote] = field(default_factory=list)


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
        plugin_logger = plugin.logger.getChild(hook_name)
        result = plugin.on_hook(hook_name, logger=plugin_logger, **kwargs)
        if result is None:
            continue
        if result.notes or result.user_notes or result.block:
            plugin_logger.info("Produced a hook result")
        merged.notes.extend(note for note in result.notes if note.strip())
        merged.user_notes.extend(result.user_notes)
        if result.block and merged.block is None:
            merged.block = result.block
    return merged


class HooksPlugin:
    """Base class for hook plugins.

    Override any methods to provide custom behaviour. All methods return
    empty/None by default so the core framework has zero built-in opinions.
    """

    @property
    def logger(self) -> logging.Logger:
        """This plugin's dedicated logger, named after its concrete class."""
        return logging.getLogger(f"hooks.{type(self).__name__}")

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

    def get_research_detail_extractors(
        self,
    ) -> dict[str, Callable[[dict[str, Any]], str]]:
        """Return per-tool detail extractors for research lookups.

        Each maps a research tool name to a callable that derives a short
        detail string (e.g. a URL or query) from that tool's parameters.

        Returns:
            Mapping of tool name to a detail-extraction callable.
        """
        return {}

    def get_tooling_note(self, workspace_roots: list[str]) -> ToolingNote | None:
        """Return this plugin's ecosystem tooling note for these workspace roots.

        A plugin supplies its own build-tool guidance here, optionally
        replacing the generic ecosystem note for the same roots.

        Args:
            workspace_roots: List of workspace root paths.

        Returns:
            None by default.
        """
        return None

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Handle any hook event, returning notes and/or a block reason.

        Args:
            hook_name: The hook event name (e.g. "TaskStart", "PreToolUse").
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult with notes/block, or None to do nothing.
        """
        return None


@dataclass(frozen=True)
class PluginMethodInfo:
    """One introspected public method of the HooksPlugin protocol.

    Attributes:
        name: The method name.
        params: The parameter list rendered as written in source, excluding
            self (e.g. "workspace_roots" or "hook_name, **kwargs").
        purpose: The method's docstring summary line.
        return_type: The method's return type annotation as written in source.
    """

    name: str
    params: str
    purpose: str
    return_type: str


def _format_param(param: inspect.Parameter) -> str:
    """Render a parameter as it appears in source, without its annotation.

    Args:
        param: The parameter to render.

    Returns:
        The parameter name, prefixed with `*`/`**` for variadic parameters.
    """
    if param.kind is inspect.Parameter.VAR_POSITIONAL:
        return f"*{param.name}"
    if param.kind is inspect.Parameter.VAR_KEYWORD:
        return f"**{param.name}"
    return param.name


def list_plugin_methods() -> list[PluginMethodInfo]:
    """List HooksPlugin's public overridable methods, in definition order.

    The single source of truth for both the generated README table and the
    plugins CLI listing's override detection.

    Returns:
        One PluginMethodInfo per public method defined directly on
        HooksPlugin, in source-definition order.
    """
    infos: list[PluginMethodInfo] = []
    for name, member in vars(HooksPlugin).items():
        if name.startswith("_") or not inspect.isfunction(member):
            continue
        sig = inspect.signature(member)
        params = ", ".join(_format_param(param) for param_name, param in sig.parameters.items() if param_name != "self")
        doc = inspect.getdoc(member) or ""
        purpose = doc.splitlines()[0] if doc else ""
        infos.append(
            PluginMethodInfo(
                name=name,
                params=params,
                purpose=purpose,
                return_type=str(sig.return_annotation),
            )
        )
    return infos


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

    loaded_bundled: list[HooksPlugin] = []

    for _finder, name, _ispkg in pkgutil.iter_modules(_plugins_pkg.__path__, _plugins_pkg.__name__ + "."):
        try:
            module = importlib.import_module(name)
            loaded_bundled.extend(
                attr()
                for attr in vars(module).values()
                if (
                    isinstance(attr, type)
                    and issubclass(attr, HooksPlugin)
                    and attr is not HooksPlugin
                    and attr.__module__ == name
                )
            )
        except Exception:
            logger.exception("Failed to load bundled plugin module: %s", name)

    loaded_external: list[HooksPlugin] = []

    for ep in importlib.metadata.entry_points(group="cline_hooks"):
        try:
            cls = ep.load()
            if isinstance(cls, type) and issubclass(cls, HooksPlugin):
                loaded_external.append(cls())
        except Exception:
            logger.exception("Failed to load external plugin: %s", ep.name)

    logger.debug("Bundled plugins: %s", ",".join([plugin.__class__.__name__ for plugin in loaded_bundled]))
    logger.debug("External plugins: %s", ",".join([plugin.__class__.__name__ for plugin in loaded_external]))

    loaded = [*loaded_bundled, *loaded_external]

    _plugin_cache.set(loaded)
    return loaded


# Deprecated alias for backward compatibility with external plugins.
ClineHooksPlugin = HooksPlugin
