from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import TYPE_CHECKING

import bashlex
import bashlex.errors

from cline_hooks.core.hook_kwargs import PreShellKwargs, PreToolUseKwargs, TrackToolUseKwargs
from cline_hooks.core.install import binary_names
from cline_hooks.core.parameters import SendMessageParameters, ShellParameters, SpawnAgentParameters
from cline_hooks.core.plugin import HookResult, HooksPlugin, is_subagent
from cline_hooks.core.state import PluginStateStore
from cline_hooks.core.vocabulary import AGENT_SPAWN_TOOLS, MESSAGE_TOOLS, SHELL_TOOLS, CanonicalHook, PluginScope
from cline_hooks.handlers.commands import ParsedCommand, extract_commands
from cline_hooks.handlers.herdr_guard import (
    ack_marker,
    ack_marker_ids,
    agent_prompts,
    handoff_prompt_marker_id,
    is_ack_only,
    is_tab_close,
    resolve_agent_pane,
    sent_handoff_marker_id,
    unwrap_peer_message,
)

if TYPE_CHECKING:
    import logging


@dataclass
class _AckState:
    """Acks a session owes after receiving a handoff, and acks it awaits after sending one."""

    owed_ack: str = ""
    awaited_acks: list[str] = field(default_factory=list)


_store: PluginStateStore[_AckState] = PluginStateStore("handoff-ack-state.json", _AckState)


def clear_acks() -> None:
    """Release every session from its owed and awaited handoff acknowledgements."""

    def clear(state: _AckState) -> None:
        state.owed_ack = ""
        state.awaited_acks.clear()

    _store.update_all(clear)


def _session_key(task_id: str) -> str:
    """Return the session a per-agent task id belongs to.

    Returns:
        The task id with any `:agent` suffix removed.
    """
    return task_id.partition(":")[0]


def _parse(command: str) -> list[ParsedCommand]:
    """Parse a shell command into its simple commands.

    Returns:
        The parsed commands, or empty if the command is blank or cannot be parsed.
    """
    if not command:
        return []
    try:
        return extract_commands(bashlex.parse(command))
    except bashlex.errors.ParsingError:
        return []


def _owed_ack_command(pane_id: str) -> str:
    return f'herdr agent prompt {pane_id} "{ack_marker(pane_id)}"'


def _is_clear_command(commands: list[ParsedCommand]) -> bool:
    """Check whether any command runs this distribution's `handoff-ack` subcommand.

    Returns:
        True if a word naming the binary or module is followed by `handoff-ack`.
    """
    names = {*binary_names(), "cline_hooks"}
    for cmd in commands:
        words = [cmd.name, *cmd.words]
        for index, word in enumerate(words):
            if Path(word).name in names and "handoff-ack" in words[index + 1 :]:
                return True
    return False


def _is_other_agent(target: str) -> bool:
    """Check that a marker target resolves to a Herdr agent other than this session's pane.

    Returns:
        True if herdr resolves the target to a pane that is not this session's own.
    """
    pane_id = resolve_agent_pane(target)
    return pane_id is not None and pane_id != os.environ.get("HERDR_PANE_ID")


def _is_own_pane(target: str) -> bool:
    """Check that a marker target is this session's own Herdr pane.

    Returns:
        True if the target is the pane id in `HERDR_PANE_ID` or resolves to it.
    """
    own_pane = os.environ.get("HERDR_PANE_ID")
    return bool(own_pane) and (target == own_pane or resolve_agent_pane(target) == own_pane)


def _sent_handoff_panes(text: str) -> list[str]:
    """Return this session's own pane if the text is a handoff prompt asking for its ack.

    Returns:
        The marker pane id in a list if it is this session's own pane, else empty.
    """
    pane_id = sent_handoff_marker_id(text)
    return [pane_id] if pane_id and _is_own_pane(pane_id) else []


def _on_user_prompt(logger: logging.Logger, **kwargs: object) -> None:
    """Release a pending handoff when its ack arrives, else owe an ack for a handoff prompt."""
    task_id = kwargs.get("task_id")
    message = kwargs.get("message")
    if not isinstance(task_id, str) or not isinstance(message, str) or is_subagent(kwargs):
        return
    pane_ids = ack_marker_ids(message)
    if not pane_ids:
        return

    key = _session_key(task_id)
    awaited = _store.get(key).awaited_acks
    handoff_pane = handoff_prompt_marker_id(unwrap_peer_message(message))
    owed = handoff_pane if handoff_pane and handoff_pane not in awaited and _is_other_agent(handoff_pane) else ""

    def apply(state: _AckState) -> None:
        for pane_id in pane_ids:
            if pane_id in state.awaited_acks:
                state.awaited_acks.remove(pane_id)
                logger.debug("Handoff acknowledged by pane %s", pane_id)
        if owed and not state.owed_ack:
            state.owed_ack = owed
            logger.debug("Handoff received: owing an ack to pane %s", owed)

    _store.update(key, apply)


def _pre_tool_use(**kwargs: object) -> HookResult | None:
    """Block every tool except the ack while a handoff ack is owed, and record handoffs sent as messages.

    The ack is the prompt command, a message carrying the marker, or a subagent spawn whose task carries the command.

    Returns:
        A blocking HookResult naming the ack command, or None.
    """
    kw = PreToolUseKwargs.build(kwargs)
    key = _session_key(kw.task_id)
    pane_id = _store.get(key).owed_ack
    text = SendMessageParameters.build(kw.parameters).text if kw.tool_name in MESSAGE_TOOLS else ""
    if not pane_id:
        sent = _sent_handoff_panes(text)
        if sent:
            _store.update(key, lambda state: state.awaited_acks.extend(p for p in sent if p not in state.awaited_acks))
        return None
    if kw.tool_name in SHELL_TOOLS and is_ack_only(_parse(ShellParameters.build(kw.parameters).command), pane_id):
        return None
    if ack_marker(pane_id) in text:
        return None
    if kw.tool_name in AGENT_SPAWN_TOOLS:
        task = SpawnAgentParameters.build(kw.parameters).task
        if _owed_ack_command(pane_id) in task:
            return None
    return HookResult(
        block=(
            f"BLOCKED until the handoff is acknowledged: MUST first run exactly "
            f"`{_owed_ack_command(pane_id)}` and nothing else. No other tool may run before it. "
            f"Without a shell tool, MUST instead spawn one subagent whose task is only to run that exact command."
        )
    )


def _track_tool_use(**kwargs: object) -> None:
    """Release the owed ack once its prompt command, ack message or subagent spawn has succeeded."""
    kw = TrackToolUseKwargs.build(kwargs)
    if kw.tool_name in SHELL_TOOLS:
        commands = _parse(ShellParameters.build(kw.parameters).command)

        def sent_ack(owed: str) -> bool:
            return is_ack_only(commands, owed)

    elif kw.tool_name in MESSAGE_TOOLS:
        text = SendMessageParameters.build(kw.parameters).text

        def sent_ack(owed: str) -> bool:
            return ack_marker(owed) in text

    elif kw.tool_name in AGENT_SPAWN_TOOLS:
        task = SpawnAgentParameters.build(kw.parameters).task

        def sent_ack(owed: str) -> bool:
            return _owed_ack_command(owed) in task

    else:
        return

    def apply(state: _AckState) -> None:
        if state.owed_ack and sent_ack(state.owed_ack):
            state.owed_ack = ""

    _store.update(_session_key(kw.task_id), apply)


def _pre_shell(logger: logging.Logger, **kwargs: object) -> HookResult | None:
    """Block clearing owed acks, record a sent handoff, and block closing the tab until its ack arrives.

    Returns:
        A blocking HookResult for an ack clear or a tab close while an ack is awaited, or None.
    """
    kw = PreShellKwargs.build(kwargs)
    commands = _parse(kw.command)
    if _is_clear_command(commands):
        return HookResult(block="Only the user may clear handoff acknowledgements. MUST NOT run this command.")
    sent = [pane_id for _, text in agent_prompts(commands) for pane_id in _sent_handoff_panes(text)]

    def apply(state: _AckState) -> str | None:
        state.awaited_acks.extend(pane_id for pane_id in sent if pane_id not in state.awaited_acks)
        return state.awaited_acks[0] if state.awaited_acks else None

    awaited = _store.update(_session_key(kw.task_id), apply) if sent else None
    if awaited is None:
        awaited = next(iter(_store.get(_session_key(kw.task_id)).awaited_acks), None)
    if awaited is None or not is_tab_close(commands):
        return None
    logger.debug("Blocked herdr tab close: handoff ack from pane %s is outstanding", awaited)
    return HookResult(
        block=(
            f"herdr tab close is blocked: the new session has not acknowledged the handoff. "
            f"MUST wait for its `{ack_marker(awaited)}` reply and MUST NOT resend the prompt. "
            f"If it never arrives, keep this tab open and report to the user."
        )
    )


class HandoffAckPlugin(HooksPlugin):
    """Bundled plugin enforcing the new-pane handoff acknowledgement handshake."""

    handles_peer_messages = True

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Dispatch user-prompt, tool and session-end events to the handshake guards.

        Args:
            hook_name: The hook or plugin-scope name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult with a block reason, or None.
        """
        if hook_name == CanonicalHook.USER_PROMPT_SUBMIT:
            _on_user_prompt(logger, **kwargs)
        elif hook_name == CanonicalHook.PRE_TOOL_USE:
            return _pre_tool_use(**kwargs)
        elif hook_name == PluginScope.PRE_SHELL:
            return _pre_shell(logger, **kwargs)
        elif hook_name == PluginScope.TRACK_TOOL_USE:
            _track_tool_use(**kwargs)
        elif hook_name in {CanonicalHook.TASK_COMPLETE, CanonicalHook.TASK_CANCEL}:
            task_id = kwargs.get("task_id")
            if isinstance(task_id, str) and not is_subagent(kwargs):
                _store.reset(_session_key(task_id))
        return None
