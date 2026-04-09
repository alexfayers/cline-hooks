from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.core.plugin import collect_hook_results, load_plugins
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

    parts: list[str] = [
        (
            f"Context compaction imminent: {hook.preCompact.conversationLength} messages, "
            f"~{hook.preCompact.estimatedTokens} tokens will be truncated."
        ),
    ]

    result = collect_hook_results(load_plugins(), "PreCompact")
    parts.extend(result.notes)

    allow(" ".join(parts))
