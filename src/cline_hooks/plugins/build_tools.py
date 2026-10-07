from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.core.plugin import HookResult, HooksPlugin, collect_contributions, hookimpl, hookspec
from cline_hooks.core.vocabulary import CanonicalHook

if TYPE_CHECKING:
    import logging

DEFAULT_BUILD_COMMANDS = frozenset({"just", "pnpm", "npm", "pytest", "flutter", "dart"})


class BuildToolsSpec:
    """Extension point for contributing build tool command names."""

    @hookspec
    def build_commands(self) -> frozenset[str]:
        """Return command names that are considered build tools.

        Returns:
            frozenset of command name strings.
        """
        raise NotImplementedError


def all_build_commands() -> frozenset[str]:
    """Return the union of the build commands every plugin contributes.

    Returns:
        frozenset of command name strings; empty if nothing contributes.
    """
    return frozenset().union(*collect_contributions(BuildToolsSpec.build_commands, frozenset))


class BuildToolsPlugin(HooksPlugin):
    """Recognises standard build tool commands and alerts on build failures."""

    hookspecs = BuildToolsSpec

    @hookimpl
    def build_commands(self) -> frozenset[str]:
        """Return the standard set of build tool command names.

        Returns:
            frozenset containing just, pnpm, npm, pytest, flutter, and dart.
        """
        return DEFAULT_BUILD_COMMANDS

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Alert when a PostToolUse shell result reports a build failure.

        Args:
            hook_name: The hook event name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult alerting on a build failure, otherwise None.
        """
        if hook_name != CanonicalHook.POST_TOOL_USE:
            return None
        tool_result = kwargs.get("tool_result")
        if isinstance(tool_result, str) and "BUILD FAILED" in tool_result:
            logger.debug("Detected build failure in tool result")
            return HookResult(notes=["The build failed! It did NOT pass. It FAILED!!"])
        return None
