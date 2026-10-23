from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cline_hooks.core.plugin import HookResult, HooksPlugin, is_subagent
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.state import PluginStateStore
from cline_hooks.core.vocabulary import CanonicalHook, TaskSource
from cline_hooks.handlers.context_nudge import with_team_clause

if TYPE_CHECKING:
    import logging

_BAND_SIZE = 10_000

CONTEXT_REDUCED_THRESHOLD = 300_000
CONTEXT_DEGRADED_THRESHOLD = 500_000
_PERCENT = 100


@dataclass
class _ContextState:
    """Per-session record of the highest context-token band already nudged."""

    band: int | None = None


_store: PluginStateStore[_ContextState] = PluginStateStore("context-state.json", _ContextState)


def _band_for(token_count: int) -> int:
    """Return the band index for a token count.

    Bands are fixed-width slices of BAND_SIZE tokens counted from zero, so band 0
    covers [0, BAND_SIZE), band 1 the next slice, and so on.

    Args:
        token_count: The current context token count.

    Returns:
        The zero-based band index.
    """
    return token_count // _BAND_SIZE


def should_nudge_context(task_id: str, token_count: int) -> bool:
    """Check whether the current token count crosses into a new context band.

    Fires once per band. The highest band already nudged for the session is
    persisted, so a nudge fires only when the count crosses into a band not yet
    nudged for this task.

    Args:
        task_id: The session or task identifier.
        token_count: The current context token count.

    Returns:
        True if the token count has entered a band not yet nudged this session.
    """
    band = _band_for(token_count)

    def decide(state: _ContextState) -> bool:
        if state.band is not None and band <= state.band:
            return False
        state.band = band
        return True

    return _store.update(task_id, decide)


def reset(task_id: str) -> None:
    """Clear the nudged-band record for a session.

    Args:
        task_id: The session or task identifier.
    """
    _store.reset(task_id)


_CONTEXT_STATUS = "CONTEXT STATUS: ~{tokens:,} tokens in use."

_CONTEXT_STATUS_WINDOW = "CONTEXT STATUS: ~{tokens:,} / {window:,} tokens ({percent:.1f}%) in use."

_CONTEXT_NUDGE_INFO = "{status} No action needed yet."

_CONTEXT_NUDGE_REDUCED = (
    f"{{status}} Accuracy degrading past {CONTEXT_REDUCED_THRESHOLD // 1000}k. MUST ask the user before "
    "starting new planning or implementation. To continue, MUST record current state in memory."
)

_CONTEXT_NUDGE_SEVERE = (
    "{status} Context budget exhausted. MUST stop new work, record current state in memory, "
    "and compact or hand off now."
)

_CONTEXT_NUDGE_REDUCED_SUBAGENT = (
    f"{{status}} Accuracy degrading past {CONTEXT_REDUCED_THRESHOLD // 1000}k. MUST report your state to "
    "your caller/lead before starting new planning or implementation. To continue, MUST record current state in "
    "memory."
)

_CONTEXT_NUDGE_SEVERE_SUBAGENT = (
    "{status} Context budget exhausted. MUST stop, report your state to your caller/lead, and ask to be replaced."
)


def _status(token_count: int, context_window: int | None) -> str:
    """Return the status sentence, with the budget and percent when the window is known.

    The budget is the window, capped at the degraded threshold, so a larger window is not revealed.
    """
    if not context_window or context_window <= 0:
        return _CONTEXT_STATUS.format(tokens=token_count)
    budget = min(context_window, CONTEXT_DEGRADED_THRESHOLD)
    return _CONTEXT_STATUS_WINDOW.format(tokens=token_count, window=budget, percent=token_count / budget * _PERCENT)


def context_note(
    task_id: str, token_count: int, *, is_subagent: bool = False, context_window: int | None = None
) -> str | None:
    """Return the context-usage nudge for the current token count, or None.

    Fires at most once per 10k-token band, from whichever call site reaches
    that band first. Every note carries the text of the tier the token count
    is in. A subagent or teammate cannot address the human user directly, so its tier
    text points it at its caller/lead instead, and skips the team-stop clause
    that only makes sense from the main agent.

    Args:
        task_id: The per-agent state key.
        token_count: The current context token count.
        is_subagent: Whether this hook fired for a subagent/teammate rather
            than the main agent.
        context_window: The model's context window in tokens, when the
            frontend reports it. The note shows usage against it, capped at
            the degraded threshold.

    Returns:
        The nudge text, or None when nothing should fire this check.
    """
    if not should_nudge_context(task_id, token_count):
        return None
    status = _status(token_count, context_window)
    if token_count >= CONTEXT_DEGRADED_THRESHOLD:
        if is_subagent:
            return _CONTEXT_NUDGE_SEVERE_SUBAGENT.format(status=status)
        return with_team_clause(_CONTEXT_NUDGE_SEVERE.format(status=status), task_id)
    if token_count >= CONTEXT_REDUCED_THRESHOLD:
        if is_subagent:
            return _CONTEXT_NUDGE_REDUCED_SUBAGENT.format(status=status)
        return with_team_clause(_CONTEXT_NUDGE_REDUCED.format(status=status), task_id)
    return _CONTEXT_NUDGE_INFO.format(status=status)


def _token_count(kwargs: dict[str, object]) -> int | None:
    """Return the frontend-reported token count, else the one its transcript reports."""
    reported = kwargs.get("context_tokens")
    if isinstance(reported, int):
        return reported
    transcript_path = kwargs.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    agent_id = kwargs.get("agent_id")
    if isinstance(agent_id, str) and agent_id:
        return get_protocol().transcript.subagent_context_tokens(transcript_path, agent_id)
    return get_protocol().transcript.context_tokens(transcript_path)


class ContextUsagePlugin(HooksPlugin):
    """Emits the per-band context-usage tier note on tool use and user prompts."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Emit the context-usage note from the transcript's token count.

        Args:
            hook_name: The hook event name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult carrying the tier note, or None.
        """
        if hook_name == CanonicalHook.TASK_START:
            task_id = kwargs.get("task_id")
            source = kwargs.get("source")
            if isinstance(task_id, str) and source != TaskSource.RESUME:
                reset(task_id)
            return None
        if hook_name in {CanonicalHook.TASK_COMPLETE, CanonicalHook.SUBAGENT_STOP}:
            task_id = kwargs.get("task_id")
            if isinstance(task_id, str) and (hook_name == CanonicalHook.TASK_COMPLETE or is_subagent(kwargs)):
                reset(task_id)
            return None
        if hook_name not in {
            CanonicalHook.POST_TOOL_USE,
            CanonicalHook.USER_PROMPT_SUBMIT,
        }:
            return None
        task_id = kwargs.get("task_id")
        if not isinstance(task_id, str):
            return None
        token_count = _token_count(kwargs)
        if token_count is None:
            return None
        context_window = kwargs.get("context_window")
        note = context_note(
            task_id,
            token_count,
            is_subagent=is_subagent(kwargs),
            context_window=context_window if isinstance(context_window, int) else None,
        )
        if note is None:
            return None
        logger.debug("Emitted context-usage note")
        return HookResult(notes=[note])
