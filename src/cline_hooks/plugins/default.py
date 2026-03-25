from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.commands import CommandRule, validate_git_commit_message
from cline_hooks.plugin import ClineHooksPlugin

if TYPE_CHECKING:
    from cline_hooks.commands import ParsedCommand

_BUILD_COMMANDS = frozenset({"just", "pnpm", "npm"})


def _requires_build_context(_cmd: ParsedCommand, all_commands: list[ParsedCommand]) -> bool:
    """Return True only when a build tool is present in the same command list."""
    return any(cmd.name in _BUILD_COMMANDS for cmd in all_commands)


class DefaultPlugin(ClineHooksPlugin):
    """Default bundled plugin providing standard cline-hooks behaviour."""

    def get_build_commands(self) -> frozenset[str]:
        """Return the standard set of build tool command names.

        Returns:
            frozenset containing just.
        """
        return _BUILD_COMMANDS

    def get_command_rules(self) -> list[CommandRule]:
        """Return the standard set of command rules.

        Returns:
            Rules for rm -f, git commit messages, and build-context grep/head/tail.
        """
        return [
            CommandRule(
                command="rm",
                blocked_flags=frozenset({"-f", "--force"}),
                message="rm -f is not allowed. Remove the -f flag.",
            ),
            CommandRule(
                command="git",
                message="Commit messages must be single-line. Do not add a body.",
                validator=validate_git_commit_message,
            ),
            CommandRule(
                command="grep",
                message="Use an MCP tool instead of grep for searching files.",
                validator=_requires_build_context,
            ),
            CommandRule(
                command="head",
                message="Do not filter build output with head - always capture the full output.",
                validator=_requires_build_context,
            ),
            CommandRule(
                command="tail",
                message="Do not filter build output with tail - always capture the full output.",
                validator=_requires_build_context,
            ),
        ]
