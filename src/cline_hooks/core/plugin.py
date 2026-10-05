from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import importlib
import importlib.metadata
import inspect
import logging
import pkgutil
from types import ModuleType
from typing import TYPE_CHECKING, ClassVar

import pluggy

import cline_hooks.plugins as _plugins_pkg

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

logger = logging.getLogger("hooks.plugin_loader")

hookspec = pluggy.HookspecMarker("cline_hooks")
hookimpl = pluggy.HookimplMarker("cline_hooks")


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


def is_subagent(kwargs: Mapping[str, object]) -> bool:
    """Return True if a hook call is running inside a spawned subagent.

    A subagent carries a non-empty agent_id, and a split-pane agent-team teammate
    carries is_teammate; the main agent loop has neither.

    Args:
        kwargs: The raw keyword arguments passed to on_hook.

    Returns:
        True for a subagent or teammate, False otherwise.
    """
    agent_id = kwargs.get("agent_id")
    return (isinstance(agent_id, str) and bool(agent_id)) or kwargs.get("is_teammate") is True


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

    Attributes:
        hookspecs: The class of @hookspec methods this plugin publishes as an
            extension point, or None if it publishes none.
    """

    hookspecs: ClassVar[type | None] = None

    @property
    def logger(self) -> logging.Logger:
        """This plugin's dedicated logger, named after its concrete class."""
        return logging.getLogger(f"hooks.{type(self).__name__}")

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


class _PluginCache:
    """Holds the cached plugin list and its plugin manager for the process lifetime."""

    def __init__(self) -> None:
        self._loaded: list[HooksPlugin] | None = None
        self._manager: pluggy.PluginManager | None = None
        self._problems: list[str] = []

    def get(self) -> list[HooksPlugin] | None:
        """Return the cached plugin list, or None if not yet loaded."""
        return self._loaded

    def get_manager(self) -> pluggy.PluginManager | None:
        """Return the plugin manager built for the cached plugin list, or None if not yet built."""
        return self._manager

    def get_problems(self) -> list[str]:
        """Return the problems recorded while loading the cached plugin list."""
        return self._problems

    def add_problem(self, problem: str) -> None:
        """Record a problem met while loading plugins."""
        self._problems.append(problem)

    def set(
        self,
        plugins: list[HooksPlugin] | None,
        manager: pluggy.PluginManager | None = None,
        problems: list[str] | None = None,
    ) -> None:
        """Store the loaded plugin list, with the manager built for it and the problems met loading it, if any."""
        self._loaded = plugins
        self._manager = manager
        self._problems = problems or []


_plugin_cache = _PluginCache()

REMOVED_PLUGIN_METHODS = (
    "get_build_commands",
    "get_command_rules",
    "get_state_write_tool_names",
    "get_research_tool_names",
    "get_research_detail_extractors",
    "get_tooling_note",
)


def _module_plugins(module: ModuleType) -> list[HooksPlugin]:
    """Instantiate the plugin classes defined in a module, ignoring imported ones.

    Args:
        module: The module to scan.

    Returns:
        One instance per HooksPlugin subclass defined in the module.
    """
    return [
        attr()
        for attr in vars(module).values()
        if (
            isinstance(attr, type)
            and issubclass(attr, HooksPlugin)
            and attr is not HooksPlugin
            and attr.__module__ == module.__name__
        )
    ]


def _package_plugins(package: ModuleType) -> list[HooksPlugin]:
    """Instantiate plugins from each submodule of a package, alphabetically, isolating import failures.

    Args:
        package: The package whose submodules to scan.

    Returns:
        The plugins from every submodule that imported successfully.
    """
    plugins: list[HooksPlugin] = []
    for name in sorted(info.name for info in pkgutil.iter_modules(package.__path__, package.__name__ + ".")):
        try:
            plugins.extend(_module_plugins(importlib.import_module(name)))
        except Exception:
            logger.exception("Failed to load plugin module: %s", name)
            _plugin_cache.add_problem(f"Plugin module {name} failed to load and is ignored")
    return plugins


def _entry_point_plugins(obj: object) -> list[HooksPlugin]:
    """Instantiate plugins from a loaded entry point naming a class, module or package.

    Args:
        obj: The object the entry point resolved to.

    Returns:
        The plugins it provides, or an empty list if it is none of the supported kinds.
    """
    if isinstance(obj, type):
        return [obj()] if issubclass(obj, HooksPlugin) else []
    if isinstance(obj, ModuleType):
        return _package_plugins(obj) if hasattr(obj, "__path__") else _module_plugins(obj)
    return []


def load_plugins() -> list[HooksPlugin]:
    """Load all plugins: bundled from cline_hooks.plugins, then external entry points.

    Entry points may name a plugin class, a module or a package, and load in
    (name, value) order. Results are cached for the lifetime of the process.

    Returns:
        List of loaded HooksPlugin instances.
    """
    cached = _plugin_cache.get()
    if cached is not None:
        return cached

    _plugin_cache.set(None)
    loaded_bundled = _package_plugins(_plugins_pkg)

    loaded_external: list[HooksPlugin] = []

    for ep in sorted(importlib.metadata.entry_points(group="cline_hooks"), key=lambda ep: (ep.name, ep.value)):
        try:
            loaded_external.extend(_entry_point_plugins(ep.load()))
        except Exception:
            logger.exception("Failed to load external plugin: %s", ep.name)
            _plugin_cache.add_problem(f"External plugin {ep.name} failed to load and is ignored")

    logger.debug("Bundled plugins: %s", ",".join([plugin.__class__.__name__ for plugin in loaded_bundled]))
    logger.debug("External plugins: %s", ",".join([plugin.__class__.__name__ for plugin in loaded_external]))

    loaded = [*loaded_bundled, *loaded_external]
    for plugin in loaded:
        for method in REMOVED_PLUGIN_METHODS:
            if hasattr(plugin, method):
                _plugin_cache.add_problem(f"{type(plugin).__name__} defines removed method {method}, which is ignored")

    _plugin_cache.set(loaded, None, _plugin_cache.get_problems())
    return loaded


def get_plugin_problems() -> list[str]:
    """Return the problems met loading plugins and registering their hookimpls.

    Returns:
        One short description per problem; empty if every plugin loaded cleanly.
    """
    get_plugin_manager()
    return list(_plugin_cache.get_problems())


def _build_plugin_manager(plugins: Sequence[HooksPlugin]) -> pluggy.PluginManager:
    """Build a plugin manager with every plugin's hookspecs added and its hookimpls registered.

    Args:
        plugins: The plugins, in registration order.

    Returns:
        A manager where a plugin whose hookimpls do not match their specs is logged and left unregistered.
    """
    manager = pluggy.PluginManager("cline_hooks")
    for plugin in plugins:
        if plugin.hookspecs is not None:
            manager.add_hookspecs(plugin.hookspecs)
    for plugin in plugins:
        try:
            manager.register(plugin)
        except pluggy.PluginValidationError:
            manager.unregister(plugin)
            plugin.logger.exception("Invalid hook implementation; plugin contributes nothing")
            _plugin_cache.add_problem(f"{type(plugin).__name__} has an invalid hook implementation and is ignored")
    return manager


def get_plugin_manager() -> pluggy.PluginManager:
    """Return the process-cached plugin manager for load_plugins().

    Returns:
        The manager holding every loaded plugin's hookspecs and hookimpls.
    """
    plugins = load_plugins()
    manager = _plugin_cache.get_manager()
    if manager is None:
        manager = _build_plugin_manager(plugins)
        _plugin_cache.set(plugins, manager, _plugin_cache.get_problems())
    return manager


@contextmanager
def plugins_override(plugins: Sequence[HooksPlugin]) -> Iterator[None]:
    """Make load_plugins() and get_plugin_manager() see exactly these plugins, restoring the previous state on exit.

    Args:
        plugins: The plugins to install.

    Yields:
        None, while the override is active.
    """
    previous = (_plugin_cache.get(), _plugin_cache.get_manager(), _plugin_cache.get_problems())
    _plugin_cache.set(list(plugins))
    try:
        yield
    finally:
        _plugin_cache.set(*previous)


def collect_contributions[T](spec: Callable[..., object], expected: type[T], **kwargs: object) -> list[T]:
    """Collect the results every plugin's hookimpl returns for an owner's hookspec.

    None, raising and wrong-typed results are skipped; the last two are logged against the contributor.

    Args:
        spec: The owner's hookspec method.
        expected: The runtime type each result must be.
        **kwargs: The spec's parameters by name.

    Returns:
        One result per contributor, tryfirst first and then last-registered first; empty if the owner is not loaded.
    """
    hook = getattr(get_plugin_manager().hook, spec.__name__, None)
    if hook is None or not hook.has_spec():
        return []
    contributions: list[T] = []
    for impl in reversed(hook.get_hookimpls()):
        contributor_logger = impl.plugin.logger.getChild(spec.__name__)
        try:
            result = impl.function(*(kwargs[name] for name in impl.argnames))
        except Exception:
            contributor_logger.exception("Contribution raised")
            continue
        if result is None:
            continue
        if not isinstance(result, expected):
            contributor_logger.error("Contribution is %s, expected %s", type(result).__name__, expected.__name__)
            continue
        contributions.append(result)
    return contributions


@dataclass(frozen=True)
class ExtensionPointInfo:
    """One introspected extension point published by a plugin.

    Attributes:
        name: The hookspec method name.
        owner: The class name of the plugin that publishes it.
        params: The parameter list rendered as written in source, excluding self.
        purpose: The method's docstring summary line.
        return_type: The method's return type annotation as written in source.
    """

    name: str
    owner: str
    params: str
    purpose: str
    return_type: str


def list_extension_points(plugins: Sequence[HooksPlugin]) -> list[ExtensionPointInfo]:
    """List the extension points the given plugins publish.

    Args:
        plugins: The plugins to inspect, in listing order.

    Returns:
        One ExtensionPointInfo per hookspec method, in definition order within each plugin.
    """
    infos: list[ExtensionPointInfo] = []
    for plugin in plugins:
        if plugin.hookspecs is None:
            continue
        for name, member in vars(plugin.hookspecs).items():
            if not inspect.isfunction(member) or not hasattr(member, "cline_hooks_spec"):
                continue
            sig = inspect.signature(member)
            doc = inspect.getdoc(member) or ""
            infos.append(
                ExtensionPointInfo(
                    name=name,
                    owner=type(plugin).__name__,
                    params=", ".join(
                        _format_param(param) for param_name, param in sig.parameters.items() if param_name != "self"
                    ),
                    purpose=doc.splitlines()[0] if doc else "",
                    return_type=str(sig.return_annotation),
                )
            )
    return infos


# Deprecated alias for backward compatibility with external plugins.
ClineHooksPlugin = HooksPlugin
