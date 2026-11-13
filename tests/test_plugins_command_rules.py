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


def _violated(rules: list[CommandRule], command: str) -> CommandRule | None:
    return check_rules(extract_commands(bashlex.parse(command)), rules)


class TestCommandRulesPluginCommitMessageContentRule:
    @pytest.mark.parametrize(
        "message",
        [
            "feat: add parser, all tests pass",
            "fix: handle empty input; build passes",
            "fix: retry the call (CI green)",
            "chore: bump deps. Checks passed.",
            "fix: lint is passing",
            "refactor: split parser - everything green",
            "fix: tests have passed",
            "chore: everything is green",
            "fix: the build was green",
            "fix: CI has succeeded",
            "chore: CI was successful",
            "fix: tests currently pass",
            "fix: CI still passes",
            "fix: make the build pass on windows, checks pass",
            "fix: ensure the build works - tests pass",
            "fix: add the retry loop (all existing tests pass)",
        ],
    )
    def test_commit_message_claiming_a_pass_is_blocked(self, rules: list[CommandRule], message: str) -> None:
        violated = _violated(rules, f'git commit -m "{message}"')
        assert violated is not None
        assert "MUST NOT claim that the build, tests, checks or CI pass" in violated.message

    @pytest.mark.parametrize(
        "message",
        [
            "feat: add parser",
            "fix: make the build pass on windows",
            "fix: ensure tests pass on Windows",
            "test: verify the build passes without network",
            "fix: skip the step if checks pass",
            "fix: stop the flaky test failing",
            "docs: explain how CI checks run",
            "fix: ensure the retry loop in the parser still handles every empty input so that all the tests pass",
            "fix: prevent tests passing without assertions",
            "fix: stop the flaky test from passing by accident when the setup is skipped",
            "feat: test pass-through of the config",
            "fix: check that tests pass",
            "fix: confirm the tests pass",
        ],
    )
    def test_commit_message_without_a_pass_claim_is_allowed(self, rules: list[CommandRule], message: str) -> None:
        assert _violated(rules, f'git commit -m "{message}"') is None

    @pytest.mark.parametrize(
        "message",
        [
            "test: add test_parses_empty_input",
            "test: rename tests/test_parser.py::test_empty",
            "test: add it('parses empty input')",
            "test: add test.each([1])('accepts input', fn)",
            "test: add describe.each([[1, 2]]) ('accepts input', fn)",
            "test: add it.each\\`a | b\\`('accepts input', fn)",
        ],
    )
    def test_commit_message_listing_a_test_name_is_blocked(self, rules: list[CommandRule], message: str) -> None:
        violated = _violated(rules, f'git commit -m "{message}"')
        assert violated is not None
        assert "MUST NOT list test names" in violated.message

    @pytest.mark.parametrize(
        "command",
        [
            "git commit -m ok -m 'tests pass'",
            "git commit --message='tests pass'",
            "git commit --message 'tests pass'",
            "git commit -m'tests pass'",
            "git commit -am 'tests pass'",
            "git -C /repo commit -m 'tests pass'",
            'git add . && git commit -m "$(cat <<EOF\ntests pass\nEOF\n)"',
        ],
    )
    def test_every_form_of_message_flag_is_checked(self, rules: list[CommandRule], command: str) -> None:
        assert _violated(rules, command) is not None

    @pytest.mark.parametrize(
        "command",
        ["git log -m 'tests pass'", "git log --grep commit -m 'tests pass'", "git commit --amend --no-edit"],
    )
    def test_other_commands_and_messageless_commits_are_allowed(self, rules: list[CommandRule], command: str) -> None:
        assert _violated(rules, command) is None

    @pytest.mark.parametrize(
        "command",
        [
            "git commit -F message.txt",
            "git commit --file message.txt",
            "git commit --file=message.txt",
            "git commit -aF message.txt",
            "git commit -Fmessage.txt",
            "git -C /repo commit -F -",
        ],
    )
    def test_commit_message_read_from_a_file_is_blocked(self, rules: list[CommandRule], command: str) -> None:
        violated = _violated(rules, command)
        assert violated is not None
        assert "inline message" in violated.message

    @pytest.mark.parametrize("command", ["git log -F pattern", "git commit -m '-Fix the parser'", "git commit -mF"])
    def test_other_uses_of_the_file_flag_letter_are_allowed(self, rules: list[CommandRule], command: str) -> None:
        assert _violated(rules, command) is None
