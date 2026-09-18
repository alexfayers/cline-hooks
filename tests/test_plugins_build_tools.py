from __future__ import annotations

import logging

from cline_hooks.plugins.build_tools import BuildToolsPlugin


class TestBuildToolsPluginBuildCommands:
    def test_contains_just(self) -> None:
        plugin = BuildToolsPlugin()
        assert "just" in plugin.get_build_commands()

    def test_contains_pytest(self) -> None:
        plugin = BuildToolsPlugin()
        assert "pytest" in plugin.get_build_commands()

    def test_contains_flutter(self) -> None:
        plugin = BuildToolsPlugin()
        assert "flutter" in plugin.get_build_commands()

    def test_contains_dart(self) -> None:
        plugin = BuildToolsPlugin()
        assert "dart" in plugin.get_build_commands()

    def test_does_not_contain_gradle(self) -> None:
        plugin = BuildToolsPlugin()
        assert "gradle" not in plugin.get_build_commands()

    def test_does_not_contain_make(self) -> None:
        plugin = BuildToolsPlugin()
        assert "make" not in plugin.get_build_commands()

    def test_does_not_contain_cargo(self) -> None:
        plugin = BuildToolsPlugin()
        assert "cargo" not in plugin.get_build_commands()


class TestBuildToolsPluginWorkspaceContext:
    def test_on_hook_returns_none_for_unhandled_hook(self) -> None:
        plugin = BuildToolsPlugin()
        assert plugin.on_hook("TaskStart", logger=logging.getLogger("test"), workspace_roots=[]) is None
