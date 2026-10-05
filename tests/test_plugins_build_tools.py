from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cline_hooks.core.plugin import HooksPlugin, hookimpl
from cline_hooks.plugins.build_tools import BuildToolsPlugin, all_build_commands

if TYPE_CHECKING:
    from collections.abc import Callable


class FakeBuildPlugin(HooksPlugin):
    @hookimpl
    def build_commands(self) -> frozenset[str]:
        return frozenset({"fakebuild"})


class TestBuildToolsPluginBuildCommands:
    def test_contributed_commands_join_the_defaults(self, use_plugins: Callable[..., None]) -> None:
        use_plugins(BuildToolsPlugin(), FakeBuildPlugin())

        assert all_build_commands() == frozenset({"just", "pnpm", "npm", "pytest", "flutter", "dart", "fakebuild"})


class TestBuildToolsPluginWorkspaceContext:
    def test_on_hook_returns_none_for_unhandled_hook(self) -> None:
        plugin = BuildToolsPlugin()
        assert plugin.on_hook("TaskStart", logger=logging.getLogger("test"), workspace_roots=[]) is None
