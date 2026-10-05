from __future__ import annotations

from typing import TYPE_CHECKING

import bashlex
import pytest

from cline_hooks.core.plugin import collect_contributions
from cline_hooks.handlers.commands import CommandRule, check_rules, extract_commands
from cline_hooks.plugins.command_rules import CommandRulesPlugin, CommandRulesSpec

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def rules(use_plugins: Callable[..., None]) -> list[CommandRule]:
    """The command rules collected with only CommandRulesPlugin loaded.

    Returns:
        Every rule the plugin contributes, in contribution order.
    """
    use_plugins(CommandRulesPlugin())
    return [
        rule for contribution in collect_contributions(CommandRulesSpec.command_rules, list) for rule in contribution
    ]


class TestCommandRulesPluginCommandRules:
    def test_includes_grep_rule(self, rules: list[CommandRule]) -> None:
        commands = [r.command for r in rules]
        assert "grep" in commands


class TestCommandRulesPluginGitCommitMessageRule:
    def test_single_line_commit_message_is_allowed(self, rules: list[CommandRule]) -> None:
        commands = extract_commands(bashlex.parse('git commit -m "single line message"'))
        assert check_rules(commands, rules) is None

    def test_multi_line_commit_message_is_blocked(self, rules: list[CommandRule]) -> None:
        commands = extract_commands(bashlex.parse('git commit -m "line one\nline two"'))
        violated = check_rules(commands, rules)
        assert violated is not None
        assert violated.command == "git"
        assert violated.message == "Commit messages MUST be single-line with no body."
