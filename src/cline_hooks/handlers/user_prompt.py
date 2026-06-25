from __future__ import annotations

from datetime import UTC, datetime
import random
import re
from typing import TYPE_CHECKING

from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.registry import hook_handler
from cline_hooks.core.response import allow
from cline_hooks.core.transcript import get_context_tokens
from cline_hooks.state.agents import agent_use_count
from cline_hooks.state.context import should_nudge_context
from cline_hooks.state.turns import increment, should_nudge_agents, should_remind

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputUserPromptSubmit

_LATE_NIGHT_START = 22
_EARLY_MORNING_END = 6
_INFO_REMINDER_CHANCE = 0.25

_CORRECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\byou should\b",
        r"\bdon'?t\b",
        r"\bplease don'?t\b",
        r"\bstop\b",
        r"\bstop doing\b",
        r"\bfrom now on\b",
        r"\bin future\b",
        r"\bgoing forward\b",
        r"\bcorrection\b",
        r"\bwrong\b",
        r"\bthat'?s not\b",
        r"\bnot like that\b",
        r"\bwhy didn'?t you\b",
        r"\byou keep\b",
        r"\byou always\b",
        r"\byou never\b",
    ]
]

_INFO_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bactually\b",
        r"\bremember that\b",
        r"\balways\b",
        r"\bnever\b",
        r"\bprefer\b",
        r"\bi prefer\b",
        r"\bnote that\b",
        r"\bremember (to|this|that|how)\b",
    ]
]

_SCOPE_CHECK_REMINDER = (
    "SESSION LENGTH CHECK: This session has reached {turns} user turns. "
    "Pause and assess: is this still one coherent change, or has scope crept? "
    "If multiple unrelated changes have accumulated, commit what's done, note remaining work as TODOs, "
    "and suggest splitting into a new session."
)

_CORRECTION_REMINDER = (
    "CORRECTION DETECTED: The user is correcting your behavior. "
    "Find and edit the relevant rule or skill SOURCE FILE now. "
    "Memory alone is not enough - rules/skills are always loaded into context, memory must be searched for."
)

_AGENT_NUDGE_REMINDER = (
    "FAN-OUT CHECK: {turns} turns in and subagent use is lagging behind this session's length. "
    "If there is non-trivial work left, parallelise with subagents (research, independent edits, verification) "
    "rather than working sequentially."
)

_CONTEXT_DEGRADED_THRESHOLD = 400_000

_CONTEXT_NUDGE_REDUCED = (
    "CONTEXT USAGE NOTICE: ~{tokens:,} tokens in use. This is not a hard limit - the window is much larger - "
    "but focus and accuracy begin to soften past ~200k tokens and degrade gradually from there. "
    "If you are at a natural stopping point, consider committing work in progress, capturing remaining work "
    "as TODOs (or persisting to memory), and starting a fresh session to continue."
)

_CONTEXT_NUDGE_SEVERE = (
    "CONTEXT USAGE VERY HIGH: ~{tokens:,} tokens in use. Past ~400k tokens focus and accuracy are badly "
    "degraded. Strongly consider wrapping up now: commit work in progress, capture remaining work as TODOs "
    "(or persist to memory), and start a fresh session to continue."
)

_INFO_REMINDER = (
    "REMINDER: Has the user said anything that should be persisted?\n"
    "Check: new information, preferences, decisions -> persist to memory."
)


def _contains_correction_signal(message: str) -> bool:
    """Check if a user message contains signals that the user is correcting behavior.

    Returns:
        True if the message matches any correction-signal pattern.
    """
    return any(pattern.search(message) for pattern in _CORRECTION_PATTERNS)


def _contains_info_signal(message: str) -> bool:
    """Check if a user message contains signals that new information should be persisted.

    Returns:
        True if the message matches any info-signal pattern.
    """
    return any(pattern.search(message) for pattern in _INFO_PATTERNS)


@hook_handler("UserPromptSubmit")
def handle_user_prompt_submit(hook: HookInputUserPromptSubmit) -> None:
    """Handle UserPromptSubmit hook events.

    Args:
        hook: The hook input data.
    """
    notes: list[str] = []

    turn_count = increment(hook.taskId)
    if should_remind(turn_count):
        notes.append(_SCOPE_CHECK_REMINDER.format(turns=turn_count))

    if should_nudge_agents(turn_count, agent_use_count(hook.taskId)):
        notes.append(_AGENT_NUDGE_REMINDER.format(turns=turn_count))

    if hook.transcriptPath:
        token_count = get_context_tokens(hook.transcriptPath)
        if token_count is not None and should_nudge_context(hook.taskId, token_count):
            template = (
                _CONTEXT_NUDGE_SEVERE
                if token_count >= _CONTEXT_DEGRADED_THRESHOLD
                else _CONTEXT_NUDGE_REDUCED
            )
            notes.append(template.format(tokens=token_count))

    hour = datetime.now(tz=UTC).hour
    if hour >= _LATE_NIGHT_START or hour < _EARLY_MORNING_END:
        notes.append("You're working late/early. Double-check before committing or making major changes.")

    message = hook.userPromptSubmit.userMessage if hook.userPromptSubmit else ""
    if _contains_correction_signal(message):
        notes.append(_CORRECTION_REMINDER)
    elif _contains_info_signal(message) or random.random() < _INFO_REMINDER_CHANCE:
        notes.append(_INFO_REMINDER)

    result = collect_hook_results(load_plugins(), "UserPromptSubmit", message=message)
    notes.extend(result.notes)

    if notes:
        allow("\n\n".join(notes))
