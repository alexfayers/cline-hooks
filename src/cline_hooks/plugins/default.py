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


def _is_standalone(_cmd: ParsedCommand, all_commands: list[ParsedCommand]) -> bool:
    """Return True when the command is the only one (not piped into something else)."""
    return len(all_commands) == 1


def _is_follow(cmd: ParsedCommand) -> bool:
    """Return True when tail is following a file (-f / -F / --follow)."""
    return any(
        flag.startswith("--follow")
        or (flag.startswith("-") and not flag.startswith("--") and ("f" in flag[1:] or "F" in flag[1:]))
        for flag in cmd.flags
    )


def _is_standalone_grep(_cmd: ParsedCommand, all_commands: list[ParsedCommand]) -> bool:
    """Return True when grep is standalone or filtering build output."""
    return len(all_commands) == 1 or _requires_build_context(_cmd, all_commands)


def _is_standalone_tail(cmd: ParsedCommand, all_commands: list[ParsedCommand]) -> bool:
    """Return True when tail is standalone reading a file, excluding live follow."""
    return len(all_commands) == 1 and not _is_follow(cmd)


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
        # Update prompts/shared/rules/hooks.md if these command rules change.
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
                validator=_is_standalone,
            ),
            CommandRule(
                command="grep",
                message="Use the Grep tool instead of grep for searching files.",
                validator=_is_standalone_grep,
            ),
            CommandRule(
                command="head",
                message="Do not filter build output with head - always capture the full output.",
                validator=_requires_build_context,
            ),
            CommandRule(
                command="head",
                message="Use the Read tool instead of head to read files.",
                validator=_is_standalone,
            ),
            CommandRule(
                command="tail",
                message="Do not filter build output with tail - always capture the full output.",
                validator=_requires_build_context,
            ),
            CommandRule(
                command="tail",
                message="Use the Read tool instead of tail to read files.",
                validator=_is_standalone_tail,
            ),
        ]
