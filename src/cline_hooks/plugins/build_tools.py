from __future__ import annotations

from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.vocabulary import CanonicalHook

DEFAULT_BUILD_COMMANDS = frozenset({"just", "pnpm", "npm", "pytest", "flutter", "dart"})


class BuildToolsPlugin(HooksPlugin):
    """Recognises standard build tool commands and alerts on build failures."""

    def get_build_commands(self) -> frozenset[str]:
        """Return the standard set of build tool command names.

        Returns:
            frozenset containing just, pnpm, npm, pytest, flutter, and dart.
        """
        return DEFAULT_BUILD_COMMANDS

    def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
        """Alert when a PostToolUse shell result reports a build failure.

        Args:
            hook_name: The hook event name.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult alerting on a build failure, otherwise None.
        """
        if hook_name != CanonicalHook.POST_TOOL_USE:
            return None
        tool_result = kwargs.get("tool_result")
        if isinstance(tool_result, str) and "BUILD FAILED" in tool_result:
            return HookResult(notes=["The build failed! It did NOT pass. It FAILED!!"])
        return None
