from __future__ import annotations

from datetime import UTC, datetime
import random
import re
from typing import TYPE_CHECKING

from cline_hooks.core.registry import hook_handler
from cline_hooks.core.response import allow

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputUserPromptSubmit

_LATE_NIGHT_START = 22
_EARLY_MORNING_END = 6
_PERSIST_REMINDER_CHANCE = 0.25

_PERSIST_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bactually\b",
        r"\byou should\b",
        r"\bremember that\b",
        r"\balways\b",
        r"\bnever\b",
        r"\bdon'?t\b",
        r"\bplease don'?t\b",
        r"\bprefer\b",
        r"\bi prefer\b",
        r"\bstop\b",
        r"\bstop doing\b",
        r"\bfrom now on\b",
        r"\bin future\b",
        r"\bgoing forward\b",
        r"\bcorrection\b",
        r"\bwrong\b",
        r"\bthat'?s not\b",
        r"\bnote that\b",
        r"\bremember (to|this|that|how)\b",
    ]
]

_PERSIST_REMINDER = (
    "REMINDER: Has the user said anything that should be persisted?\n"
    "Check: preferences, decisions, corrections -> persist to memory or config."
)


def _contains_persist_signal(message: str) -> bool:
    """Check if a user message contains signals that new information should be persisted.

    Args:
        message: The user's message text.

    Returns:
        True if the message matches any persist-signal pattern.
    """
    return any(pattern.search(message) for pattern in _PERSIST_PATTERNS)


@hook_handler("UserPromptSubmit")
def handle_user_prompt_submit(hook: HookInputUserPromptSubmit) -> None:
    """Handle UserPromptSubmit hook events.

    Args:
        hook: The hook input data.
    """
    notes: list[str] = []

    hour = datetime.now(tz=UTC).hour
    if hour >= _LATE_NIGHT_START or hour < _EARLY_MORNING_END:
        notes.append("You're working late/early. Double-check before committing or making major changes.")

    message = hook.userPromptSubmit.userMessage if hook.userPromptSubmit else ""
    if _contains_persist_signal(message) or random.random() < _PERSIST_REMINDER_CHANCE:
        notes.append(_PERSIST_REMINDER)

    if notes:
        allow("\n\n".join(notes))
