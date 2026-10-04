from __future__ import annotations

import bashlex

from cline_hooks.handlers.commands import CommandRule, check_rules, extract_commands
from cline_hooks.plugins.command_rules import CommandRulesPlugin


class TestCommandRulesPluginBuildCommands:
    def test_does_not_contain_gradle(self) -> None:
        plugin = CommandRulesPlugin()
        assert "gradle" not in plugin.get_build_commands()

    def test_does_not_contain_make(self) -> None:
        plugin = CommandRulesPlugin()
        assert "make" not in plugin.get_build_commands()

    def test_does_not_contain_cargo(self) -> None:
        plugin = CommandRulesPlugin()
        assert "cargo" not in plugin.get_build_commands()


class TestCommandRulesPluginCommandRules:
    def test_returns_command_rules(self) -> None:
        plugin = CommandRulesPlugin()
        rules = plugin.get_command_rules()
        assert all(isinstance(r, CommandRule) for r in rules)

    def test_includes_rm_rule(self) -> None:
        plugin = CommandRulesPlugin()
        commands = [r.command for r in plugin.get_command_rules()]
        assert "rm" in commands

    def test_includes_git_rule(self) -> None:
        plugin = CommandRulesPlugin()
        commands = [r.command for r in plugin.get_command_rules()]
        assert "git" in commands

    def test_includes_grep_rule(self) -> None:
        plugin = CommandRulesPlugin()
        commands = [r.command for r in plugin.get_command_rules()]
        assert "grep" in commands


class TestCommandRulesPluginGitCommitMessageRule:
    def test_single_line_commit_message_is_allowed(self) -> None:
        plugin = CommandRulesPlugin()
        commands = extract_commands(bashlex.parse('git commit -m "single line message"'))
        assert check_rules(commands, plugin.get_command_rules()) is None

    def test_multi_line_commit_message_is_blocked(self) -> None:
        plugin = CommandRulesPlugin()
        commands = extract_commands(bashlex.parse('git commit -m "line one\nline two"'))
        violated = check_rules(commands, plugin.get_command_rules())
        assert violated is not None
        assert violated.command == "git"
        assert violated.message == "Commit messages MUST be single-line with no body."
