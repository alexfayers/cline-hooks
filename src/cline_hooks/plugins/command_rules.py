from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.core.plugin import HooksPlugin
from cline_hooks.handlers.commands import CommandRule
from cline_hooks.plugins.build_tools import DEFAULT_BUILD_COMMANDS

if TYPE_CHECKING:
    from cline_hooks.handlers.commands import ParsedCommand


def validate_git_commit_message(cmd: ParsedCommand, _all: list[ParsedCommand]) -> bool:
    """Check if a git commit message contains newlines.

    Returns:
        bool: True if the message is invalid (contains newlines).
    """
    if "commit" not in cmd.args:
        return False

    for flag in cmd.flags:
        if flag in {"-m", "--message"}:
            msg_idx = (
                cmd.flags.index(flag)
                + 1
                + len(
                    [a for a in cmd.args if cmd.args.index(a) < cmd.flags.index(flag)]
                )
            )
            all_words = cmd.args + cmd.flags
            if msg_idx < len(all_words):
                message = all_words[msg_idx]
                return "\n" in message
        elif flag.startswith("--message="):
            message = flag[10:]
            return "\n" in message

    return False


def _requires_build_context(
    _cmd: ParsedCommand, all_commands: list[ParsedCommand]
) -> bool:
    """Return True only when a build tool is present in the same command list."""
    return any(cmd.name in DEFAULT_BUILD_COMMANDS for cmd in all_commands)


def _is_standalone(_cmd: ParsedCommand, all_commands: list[ParsedCommand]) -> bool:
    """Return True when the command is the only one (not piped into something else)."""
    return len(all_commands) == 1


def _is_follow(cmd: ParsedCommand) -> bool:
    """Return True when tail is following a file (-f / -F / --follow)."""
    return any(
        flag.startswith("--follow")
        or (
            flag.startswith("-")
            and not flag.startswith("--")
            and ("f" in flag[1:] or "F" in flag[1:])
        )
        for flag in cmd.flags
    )


def _is_standalone_tail(cmd: ParsedCommand, all_commands: list[ParsedCommand]) -> bool:
    """Return True when tail is standalone reading a file, excluding live follow."""
    return len(all_commands) == 1 and not _is_follow(cmd)


class CommandRulesPlugin(HooksPlugin):
    """Standard shell-safety command rules (rm -f, commit messages, build output)."""

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
                message="rm -f is not allowed. MUST drop the -f flag.",
            ),
            CommandRule(
                command="git",
                message="Commit messages MUST be single-line with no body.",
                validator=validate_git_commit_message,
            ),
            CommandRule(
                command="cat",
                message="MUST read files with the Read tool, not cat.",
                validator=_is_standalone,
            ),
            CommandRule(
                command="grep",
                message="MUST NOT filter build output with grep - MUST capture the full output.",
                validator=_requires_build_context,
            ),
            CommandRule(
                command="head",
                message="MUST NOT filter build output with head - MUST capture the full output.",
                validator=_requires_build_context,
            ),
            CommandRule(
                command="head",
                message="MUST read files with the Read tool, not head.",
                validator=_is_standalone,
            ),
            CommandRule(
                command="tail",
                message="MUST NOT filter build output with tail - MUST capture the full output.",
                validator=_requires_build_context,
            ),
            CommandRule(
                command="tail",
                message="MUST read files with the Read tool, not tail.",
                validator=_is_standalone_tail,
            ),
            CommandRule(
                command="true",
                message=(
                    "MUST NOT use `true` as a standalone command. When waiting on a background agent "
                    "or task, MUST end your turn - a completion notification resumes you "
                    "automatically."
                ),
                validator=_is_standalone,
            ),
            CommandRule(
                command="echo",
                message=(
                    "MUST NOT use echo as a standalone command, or use it to pass time while waiting "
                    "on a background task. MUST output text directly instead of echoing it."
                ),
                validator=_is_standalone,
            ),
        ]
