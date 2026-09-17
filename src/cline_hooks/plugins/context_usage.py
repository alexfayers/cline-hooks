from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.state import PluginStateStore
from cline_hooks.core.vocabulary import NO_RESET_TASK_START_SOURCES, CanonicalHook
from cline_hooks.handlers.context_nudge import with_team_clause

if TYPE_CHECKING:
    import logging

_BAND_SIZE = 10_000

CONTEXT_REDUCED_THRESHOLD = 300_000
CONTEXT_DEGRADED_THRESHOLD = 500_000
_BOUNDARIES: tuple[int, ...] = (CONTEXT_REDUCED_THRESHOLD, CONTEXT_DEGRADED_THRESHOLD)


@dataclass
class _ContextState:
    """Per-session context-token banding and degradation-boundary record."""

    band: int | None = None
    boundary: int = 0


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
    state = _store.get(task_id)
    if state.band is not None and band <= state.band:
        return False
    state.band = band
    _store.set(task_id, state)
    return True


def crossed_boundary(task_id: str, token_count: int) -> int | None:
    """Return the degradation boundary newly crossed by this token count, or None.

    Fires once per boundary per session: later calls at or above a boundary
    already announced return None.

    Args:
        task_id: The session or task identifier.
        token_count: The current context token count.

    Returns:
        The boundary just crossed, or None if no new boundary was reached.
    """
    state = _store.get(task_id)
    newly_crossed = [b for b in _BOUNDARIES if token_count >= b > state.boundary]
    if not newly_crossed:
        return None
    boundary = max(newly_crossed)
    state.boundary = boundary
    _store.set(task_id, state)
    return boundary


def reset(task_id: str) -> None:
    """Clear the nudged-band and boundary record for a session.

    Args:
        task_id: The session or task identifier.
    """
    _store.reset(task_id)


_CONTEXT_STATUS = "CONTEXT STATUS: ~{tokens:,} tokens in use."

_CONTEXT_NUDGE_INFO = f"{_CONTEXT_STATUS} No action needed yet."

_CONTEXT_NUDGE_REDUCED = (
    f"{_CONTEXT_STATUS} Accuracy degrading past {CONTEXT_REDUCED_THRESHOLD // 1000}k. MUST ask the user before "
    "starting new planning or implementation. To continue, MUST record current state in memory."
)

_CONTEXT_NUDGE_SEVERE = (
    f"{_CONTEXT_STATUS} Accuracy badly degraded. MUST push back on new work - record current state in memory "
    "and hand off to a fresh session unless told to continue."
)


def context_note(task_id: str, token_count: int) -> str | None:
    """Return the context-usage nudge for the current token count, or None.

    Fires at most once per 10k-token band, from whichever call site reaches
    that band first. The longer per-tier text is appended only on the note
    that first crosses into that tier; later same-tier notes stay short.

    Args:
        task_id: The session or task identifier.
        token_count: The current context token count.

    Returns:
        The nudge text, or None when nothing should fire this check.
    """
    if not should_nudge_context(task_id, token_count):
        return None
    boundary = crossed_boundary(task_id, token_count)
    if boundary == CONTEXT_DEGRADED_THRESHOLD:
        return with_team_clause(_CONTEXT_NUDGE_SEVERE.format(tokens=token_count), task_id)
    if boundary == CONTEXT_REDUCED_THRESHOLD:
        return with_team_clause(_CONTEXT_NUDGE_REDUCED.format(tokens=token_count), task_id)
    return _CONTEXT_NUDGE_INFO.format(tokens=token_count)


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
            if isinstance(task_id, str) and source not in NO_RESET_TASK_START_SOURCES:
                reset(task_id)
            return None
        if hook_name == CanonicalHook.TASK_COMPLETE:
            task_id = kwargs.get("task_id")
            if isinstance(task_id, str):
                reset(task_id)
            return None
        if hook_name not in {
            CanonicalHook.POST_TOOL_USE,
            CanonicalHook.USER_PROMPT_SUBMIT,
        }:
            return None
        task_id = kwargs.get("task_id")
        transcript_path = kwargs.get("transcript_path")
        if not isinstance(task_id, str) or not isinstance(transcript_path, str):
            return None
        if not transcript_path:
            return None
        token_count = get_protocol().transcript.context_tokens(transcript_path)
        if token_count is None:
            return None
        note = context_note(task_id, token_count)
        if note is None:
            return None
        logger.debug("Emitted context-usage note")
        return HookResult(notes=[note])
