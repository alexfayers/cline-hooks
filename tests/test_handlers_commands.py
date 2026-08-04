from __future__ import annotations

import bashlex

from cline_hooks.handlers.commands import ParsedCommand, extract_commands, is_git_push


class TestExtractCommands:
    def test_uses_basename_for_absolute_path_commands(self) -> None:
        commands = extract_commands(bashlex.parse("/usr/bin/git push"))
        assert commands == [ParsedCommand(name="git", flags=[], args=["push"])]

    def test_uses_bare_name_unchanged(self) -> None:
        commands = extract_commands(bashlex.parse("git push"))
        assert commands == [ParsedCommand(name="git", flags=[], args=["push"])]


class TestIsGitPush:
    def test_detects_git_push(self) -> None:
        commands = [ParsedCommand(name="git", flags=[], args=["push"])]
        assert is_git_push(commands) is True

    def test_ignores_other_git_subcommands(self) -> None:
        commands = [ParsedCommand(name="git", flags=[], args=["commit"])]
        assert is_git_push(commands) is False

    def test_ignores_non_git_commands(self) -> None:
        commands = [ParsedCommand(name="push", flags=[], args=[])]
        assert is_git_push(commands) is False

    def test_detects_git_push_among_other_commands(self) -> None:
        commands = [
            ParsedCommand(name="cd", flags=[], args=["subdir"]),
            ParsedCommand(name="git", flags=[], args=["push"]),
        ]
        assert is_git_push(commands) is True
