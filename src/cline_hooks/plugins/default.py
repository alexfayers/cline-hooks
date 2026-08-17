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
            Rules for rm -f, git commit messages, build-context grep/head/tail, and
            standalone true/echo.
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
                message="Do not filter build output with grep - always capture the full output.",
                validator=_requires_build_context,
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
            CommandRule(
                command="true",
                message=(
                    "`true` is not allowed as a standalone command. If you're waiting on a background "
                    "agent or task, end your turn instead - a completion notification will resume you "
                    "automatically."
                ),
                validator=_is_standalone,
            ),
            CommandRule(
                command="echo",
                message=(
                    "echo is not allowed as a standalone command. Output text directly instead of "
                    "echoing it, and never use echo to pass time while waiting on a background task."
                ),
                validator=_is_standalone,
            ),
        ]
