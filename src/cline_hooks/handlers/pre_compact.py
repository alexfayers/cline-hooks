from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.core.outcome import Outcome
from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.registry import hook_handler
from cline_hooks.core.vocabulary import CanonicalHook

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputPreCompact


@hook_handler(CanonicalHook.PRE_COMPACT)
def handle_pre_compact(hook: HookInputPreCompact) -> Outcome:
    """Handle PreCompact hook events.

    Args:
        hook: The hook input data.

    Returns:
        The merged Outcome for this compaction event.
    """
    if hook.preCompact is None:
        return Outcome()

    parts: list[str] = [
        (
            f"Context compaction imminent: {hook.preCompact.conversationLength} messages, "
            f"~{hook.preCompact.estimatedTokens} tokens will be truncated."
        ),
    ]

    result = collect_hook_results(
        load_plugins(),
        "PreCompact",
        task_id=hook.taskId,
        conversation_length=hook.preCompact.conversationLength,
        estimated_tokens=hook.preCompact.estimatedTokens,
    )
    parts.extend(result.notes)

    return Outcome.allow(" ".join(parts), label="REMINDER")
