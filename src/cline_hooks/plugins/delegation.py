"""Nudge the main session to delegate its first unit of work to a teammate."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

import bashlex
import bashlex.errors

from cline_hooks.config import agent_teams_enabled
from cline_hooks.core.hook_kwargs import PreShellKwargs, PreToolUseKwargs
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.state import PluginStateStore
from cline_hooks.core.vocabulary import (
    FILE_EDIT_TOOLS,
    NO_RESET_TASK_START_SOURCES,
    CanonicalHook,
    PluginScope,
)
from cline_hooks.handlers.commands import extract_commands
from cline_hooks.state.agents import has_agent_use

if TYPE_CHECKING:
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
    state = _store.get(task_id)
    if state.nudged:
        return False
    state.nudged = True
    _store.set(task_id, state)
    return True


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
    "env",
    "printenv",
    "jq",
    "diff",
    "du",
    "df",
    "cd",
})
_READ_ONLY_GIT_SUBCOMMANDS = frozenset({
    "status",
    "log",
    "diff",
    "show",
    "branch",
    "blame",
    "remote",
    "rev-parse",
    "ls-files",
})

_DELEGATION_NUDGE = (
    "DELEGATION CHECK: An agent team is enabled and this session is about to do work "
    "inline with no subagent spawned yet. MUST delegate the first unit of work - "
    "research, design, edits, verification - to a teammate and keep this session on "
    "orchestration. MAY proceed inline where this is genuinely a one-line change or a "
    "check that costs less than the delegation - this is a default, not a block."
)


def _is_read_only_git(cmd: ParsedCommand) -> bool:
    """Check whether a parsed `git` invocation only reads repo state.

    Returns:
        True if the first non-flag argument is a known read-only subcommand.
    """
    subcommand = cmd.args[0] if cmd.args else None
    return subcommand in _READ_ONLY_GIT_SUBCOMMANDS


def _is_read_only_single(cmd: ParsedCommand) -> bool:
    """Check whether a single parsed command only reads state.

    Returns:
        True if the command name (or, for git, its subcommand) is read-only.
    """
    if cmd.name == "git":
        return _is_read_only_git(cmd)
    return cmd.name in _READ_ONLY_COMMANDS


def _is_read_only_command(command: str) -> bool:
    """Check whether a shell command line only reads state.

    A redirect (`>`) is treated as mutating even though bashlex's parsed form
    hides it, and an unparseable or empty command is treated as read-only so a
    classification failure never falsely fires the nudge.

    Returns:
        True if every parsed command in the line is read-only.
    """
    if ">" in command:
        return False
    commands: list[ParsedCommand] = []
    with contextlib.suppress(bashlex.errors.ParsingError):
        commands = extract_commands(bashlex.parse(command))
    if not commands:
        return True
    return all(_is_read_only_single(cmd) for cmd in commands)


class DelegationPlugin(HooksPlugin):
    """Nudges the main session to delegate its first unit of work to a teammate."""

    def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
        """Fire a one-shot delegation nudge before the first inline edit/write/mutating-shell call.

        Args:
            hook_name: The hook or plugin-scope name.
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
            if shell_kwargs.agent_type or has_agent_use(shell_kwargs.task_id):
                return None
            if not shell_kwargs.command or _is_read_only_command(shell_kwargs.command):
                return None
            task_id = shell_kwargs.task_id
        else:
            tool_kwargs = PreToolUseKwargs.build(kwargs)
            if tool_kwargs.agent_type or has_agent_use(tool_kwargs.task_id):
                return None
            if tool_kwargs.tool_name not in FILE_EDIT_TOOLS:
                return None
            task_id = tool_kwargs.task_id

        if not should_nudge_inline_work(task_id):
            return None
        return HookResult(notes=[_DELEGATION_NUDGE])
