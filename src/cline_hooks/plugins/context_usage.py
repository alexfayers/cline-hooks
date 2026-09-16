from __future__ import annotations

from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.vocabulary import CanonicalHook
from cline_hooks.handlers.context_nudge import with_team_clause
from cline_hooks.state.context import (
    CONTEXT_DEGRADED_THRESHOLD,
    CONTEXT_REDUCED_THRESHOLD,
    crossed_boundary,
    should_nudge_context,
)

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
        return with_team_clause(
            _CONTEXT_NUDGE_SEVERE.format(tokens=token_count), task_id
        )
    if boundary == CONTEXT_REDUCED_THRESHOLD:
        return with_team_clause(
            _CONTEXT_NUDGE_REDUCED.format(tokens=token_count), task_id
        )
    return _CONTEXT_NUDGE_INFO.format(tokens=token_count)


class ContextUsagePlugin(HooksPlugin):
    """Emits the per-band context-usage tier note on tool use and user prompts."""

    def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
        """Emit the context-usage note from the transcript's token count.

        Args:
            hook_name: The hook event name.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult carrying the tier note, or None.
        """
        if hook_name not in (
            CanonicalHook.POST_TOOL_USE,
            CanonicalHook.USER_PROMPT_SUBMIT,
        ):
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
        return HookResult(notes=[note])
