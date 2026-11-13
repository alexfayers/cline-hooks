"""Nudge the main session to delegate its first unit of work to a teammate."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
import re
import shlex
from typing import TYPE_CHECKING

from cline_hooks.config import agent_teams_enabled
from cline_hooks.core.hook_kwargs import PreShellKwargs, PreToolUseKwargs
from cline_hooks.core.plugin import HookResult, HooksPlugin, is_subagent
from cline_hooks.core.state import PluginStateStore
from cline_hooks.core.vocabulary import (
    FILE_EDIT_TOOLS,
    NO_RESET_TASK_START_SOURCES,
    CanonicalHook,
    PluginScope,
)
from cline_hooks.handlers.commands import extract_commands, is_print_only_sed, is_read_only_gh, is_read_only_git
from cline_hooks.state.agents import has_agent_use

if TYPE_CHECKING:
    import logging

    from cline_hooks.handlers.commands import ParsedCommand


@dataclass
class _DelegationState:
    """Whether the one-shot inline-work delegation nudge has fired for a session."""

    nudged: bool = False


_store: PluginStateStore[_DelegationState] = PluginStateStore("delegation-state.json", _DelegationState)


def should_nudge_inline_work(task_id: str) -> bool:
    """Check whether the inline-work delegation nudge should fire, consuming it.

    Fires True the first time it is called for a session; every subsequent
    call for the same session returns False.

    Args:
        task_id: The session or task identifier.

    Returns:
        True only on the first call for this task_id.
    """

    def decide(state: _DelegationState) -> bool:
        if state.nudged:
            return False
        state.nudged = True
        return True

    return _store.update(task_id, decide)


def reset(task_id: str) -> None:
    """Clear the delegation-nudge record for a session.

    Args:
        task_id: The session or task identifier.
    """
    _store.reset(task_id)


_READ_ONLY_COMMANDS = frozenset({
    "ls",
    "pwd",
    "cat",
    "head",
    "tail",
    "wc",
    "stat",
    "file",
    "tree",
    "find",
    "grep",
    "rg",
    "fd",
    "which",
    "echo",
    "date",
    "printenv",
    "jq",
    "diff",
    "du",
    "df",
    "cd",
})
_QUOTED_TEXT = re.compile(r"\\.|'[^']*'|\"(?:\\.|[^\"\\])*\"")
_NON_FILE_OUTPUT = re.compile(r"(?:^|\s)#[^\n]*|\d*>&\d+-?|&?\d*>>?\s*/dev/null(?=$|[\s;&|)])")
_ENV_OPTIONS_TAKING_A_VALUE = frozenset({"-u", "--unset", "-C", "--chdir"})
_MUTATING_FLAGS = {
    "find": frozenset({"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"}),
    "fd": frozenset({"-x", "--exec", "-X", "--exec-batch"}),
}

_DELEGATION_NUDGE = (
    "DELEGATION CHECK: An agent team is enabled and this session is about to do work "
    "inline with no subagent spawned yet. MUST delegate the first unit of work - "
    "research, design, edits, verification - to a teammate and keep this session on "
    "orchestration."
)


def _env_wrapped_command(words: list[str]) -> list[str]:
    """Drop the options and assignments `env` takes before the command it runs.

    Returns:
        The wrapped command and its arguments, empty if `env` only prints the environment.
    """
    remaining = iter(words)
    for word in remaining:
        if word in _ENV_OPTIONS_TAKING_A_VALUE:
            next(remaining, None)
        elif not (word.startswith("-") or "=" in word):
            return [word, *remaining]
    return []


def _is_read_only_single(cmd: ParsedCommand) -> bool:
    """Check whether a single parsed command only reads state.

    Returns:
        True if the command name (or, for git and gh, its subcommand; for sed, its script) is read-only
        and it carries no flag that runs or writes.
    """
    if cmd.name == "git":
        return is_read_only_git(cmd)
    if cmd.name == "gh":
        return is_read_only_gh(cmd)
    if cmd.name == "sed":
        return is_print_only_sed(cmd)
    if cmd.name == "env":
        wrapped = _env_wrapped_command(cmd.words)
        return not wrapped or is_read_only_command(shlex.join(wrapped))
    option_names = {word.partition("=")[0] for word in cmd.words}
    return cmd.name in _READ_ONLY_COMMANDS and _MUTATING_FLAGS.get(cmd.name, frozenset()).isdisjoint(option_names)


def is_read_only_command(command: str) -> bool:
    """Check whether a shell command line only reads state.

    An unquoted redirect (`>`) to a file is treated as mutating even though bashlex's parsed form
    hides it, and an unparseable or empty command is treated as read-only so a
    classification failure never falsely fires the nudge.

    Returns:
        True if every parsed command in the line is read-only.
    """
    if not command:
        return True
    if ">" in _NON_FILE_OUTPUT.sub(" ", _QUOTED_TEXT.sub("", command)):
        return False
    import bashlex.errors  # ruff: ignore[import-outside-top-level]

    commands: list[ParsedCommand] = []
    with contextlib.suppress(bashlex.errors.ParsingError, NotImplementedError):
        commands = extract_commands(bashlex.parse(command))
    if not commands:
        return True
    return all(_is_read_only_single(cmd) for cmd in commands)


class DelegationPlugin(HooksPlugin):
    """Nudges the main session to delegate its first unit of work to a teammate."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Fire a one-shot delegation nudge before the first inline edit/write/mutating-shell call.

        Args:
            hook_name: The hook or plugin-scope name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult carrying the nudge, or None.
        """
        if hook_name == CanonicalHook.TASK_START:
            task_id = kwargs.get("task_id")
            source = kwargs.get("source")
            if isinstance(task_id, str) and source not in NO_RESET_TASK_START_SOURCES:
                reset(task_id)
            return None
        if hook_name not in {CanonicalHook.PRE_TOOL_USE, PluginScope.PRE_SHELL}:
            return None
        if not agent_teams_enabled():
            return None

        if hook_name == PluginScope.PRE_SHELL:
            shell_kwargs = PreShellKwargs.build(kwargs)
            if is_subagent(kwargs) or has_agent_use(shell_kwargs.task_id):
                return None
            if is_read_only_command(shell_kwargs.command):
                return None
            task_id = shell_kwargs.task_id
        else:
            tool_kwargs = PreToolUseKwargs.build(kwargs)
            if is_subagent(kwargs) or has_agent_use(tool_kwargs.task_id):
                return None
            if tool_kwargs.tool_name not in FILE_EDIT_TOOLS:
                return None
            task_id = tool_kwargs.task_id

        if not should_nudge_inline_work(task_id):
            return None
        logger.debug("Fired inline-work delegation nudge")
        return HookResult(notes=[_DELEGATION_NUDGE])
