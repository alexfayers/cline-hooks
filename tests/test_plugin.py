from __future__ import annotations

from unittest.mock import patch


from cline_hooks.commands import (
    CommandRule,
    get_all_build_commands,
    get_all_command_rules,
)
from cline_hooks.plugin import ClineHooksPlugin, load_plugins
from cline_hooks.plugins.default import DefaultPlugin


class TestClineHooksPluginDefaults:
    def test_get_build_commands_returns_empty(self) -> None:
        plugin = ClineHooksPlugin()
        assert plugin.get_build_commands() == frozenset()

    def test_get_command_rules_returns_empty(self) -> None:
        plugin = ClineHooksPlugin()
        assert plugin.get_command_rules() == []

    def test_get_workspace_context_returns_none(self) -> None:
        plugin = ClineHooksPlugin()
        assert plugin.get_workspace_context([]) is None

    def test_validate_mcp_tool_returns_none(self) -> None:
        plugin = ClineHooksPlugin()
        assert plugin.validate_mcp_tool("any_tool", {}) is None


class TestLoadPlugins:
    def test_returns_list(self) -> None:
        with patch("cline_hooks.plugin._plugins", None):
            plugins = load_plugins()
        assert isinstance(plugins, list)

    def test_includes_default_plugin(self) -> None:
        with patch("cline_hooks.plugin._plugins", None):
            plugins = load_plugins()
        assert any(isinstance(p, DefaultPlugin) for p in plugins)

    def test_result_is_cached(self) -> None:
        with patch("cline_hooks.plugin._plugins", None):
            first = load_plugins()
            second = load_plugins()
        assert first is second

    def test_cache_reset_reloads(self) -> None:
        with patch("cline_hooks.plugin._plugins", None):
            plugins = load_plugins()
        assert plugins is not None


class TestDefaultPluginBuildCommands:
    def test_contains_just(self) -> None:
        plugin = DefaultPlugin()
        assert "just" in plugin.get_build_commands()

    def test_does_not_contain_brazil_build(self) -> None:
        plugin = DefaultPlugin()
        assert "brazil-build" not in plugin.get_build_commands()

    def test_does_not_contain_eda(self) -> None:
        plugin = DefaultPlugin()
        assert "eda" not in plugin.get_build_commands()

    def test_does_not_contain_bb(self) -> None:
        plugin = DefaultPlugin()
        assert "bb" not in plugin.get_build_commands()


class TestDefaultPluginCommandRules:
    def test_returns_command_rules(self) -> None:
        plugin = DefaultPlugin()
        rules = plugin.get_command_rules()
        assert all(isinstance(r, CommandRule) for r in rules)

    def test_includes_rm_rule(self) -> None:
        plugin = DefaultPlugin()
        commands = [r.command for r in plugin.get_command_rules()]
        assert "rm" in commands

    def test_includes_git_rule(self) -> None:
        plugin = DefaultPlugin()
        commands = [r.command for r in plugin.get_command_rules()]
        assert "git" in commands

    def test_includes_grep_rule(self) -> None:
        plugin = DefaultPlugin()
        commands = [r.command for r in plugin.get_command_rules()]
        assert "grep" in commands


class TestDefaultPluginWorkspaceContext:
    def test_returns_none(self) -> None:
        plugin = DefaultPlugin()
        assert plugin.get_workspace_context([]) is None


class TestGetAllBuildCommands:
    def test_empty_plugins_returns_empty(self) -> None:
        assert get_all_build_commands([]) == frozenset()

    def test_aggregates_from_multiple_plugins(self) -> None:
        class PluginA(ClineHooksPlugin):
            def get_build_commands(self) -> frozenset[str]:
                return frozenset({"make"})

        class PluginB(ClineHooksPlugin):
            def get_build_commands(self) -> frozenset[str]:
                return frozenset({"gradle"})

        result = get_all_build_commands([PluginA(), PluginB()])
        assert result == frozenset({"make", "gradle"})

    def test_deduplicates_commands(self) -> None:
        class PluginA(ClineHooksPlugin):
            def get_build_commands(self) -> frozenset[str]:
                return frozenset({"make"})

        class PluginB(ClineHooksPlugin):
            def get_build_commands(self) -> frozenset[str]:
                return frozenset({"make"})

        result = get_all_build_commands([PluginA(), PluginB()])
        assert result == frozenset({"make"})


class TestGetAllCommandRules:
    def test_empty_plugins_returns_empty(self) -> None:
        assert get_all_command_rules([]) == []

    def test_aggregates_rules_in_order(self) -> None:
        rule_a = CommandRule(command="foo", message="foo blocked")
        rule_b = CommandRule(command="bar", message="bar blocked")

        class PluginA(ClineHooksPlugin):
            def get_command_rules(self) -> list[CommandRule]:
                return [rule_a]

        class PluginB(ClineHooksPlugin):
            def get_command_rules(self) -> list[CommandRule]:
                return [rule_b]

        result = get_all_command_rules([PluginA(), PluginB()])
        assert result == [rule_a, rule_b]
