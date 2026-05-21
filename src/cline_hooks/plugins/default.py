from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.core.plugin import HooksPlugin
from cline_hooks.handlers.commands import CommandRule, validate_git_commit_message

if TYPE_CHECKING:
    from cline_hooks.handlers.commands import ParsedCommand

_BUILD_COMMANDS = frozenset({"just", "pnpm", "npm"})


def _requires_build_context(_cmd: ParsedCommand, all_commands: list[ParsedCommand]) -> bool:
    """Return True only when a build tool is present in the same command list."""
    return any(cmd.name in _BUILD_COMMANDS for cmd in all_commands)


def _is_standalone_cat(_cmd: ParsedCommand, all_commands: list[ParsedCommand]) -> bool:
    """Return True when cat is the only command (not piped into something else)."""
    return len(all_commands) == 1


class DefaultPlugin(HooksPlugin):
    """Default bundled plugin providing standard hook behaviour."""

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
                command="cat",
                message="Use the Read tool instead of cat to read files.",
                validator=_is_standalone_cat,
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
