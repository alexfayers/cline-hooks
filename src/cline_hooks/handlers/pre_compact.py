from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.core.registry import hook_handler
from cline_hooks.core.response import allow

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputPreCompact


@hook_handler("PreCompact")
def handle_pre_compact(hook: HookInputPreCompact) -> None:
    """Handle PreCompact hook events.

    Args:
        hook: The hook input data.
    """
    if hook.preCompact is None:
        return

    message = (
        f"Context compaction imminent: {hook.preCompact.conversationLength} messages, "
        f"~{hook.preCompact.estimatedTokens} tokens will be truncated. "
        "Save any important context, decisions, or progress to memory NOW before it's lost."
    )
    allow(message)
