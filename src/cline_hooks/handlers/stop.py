from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.registry import hook_handler
from cline_hooks.core.response import allow, feedback
from cline_hooks.core.vocabulary import CanonicalHook

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputStop


@hook_handler(CanonicalHook.STOP)
def handle_stop(hook: HookInputStop) -> None:
    """Handle Stop hook events by dispatching to plugins.

    Args:
        hook: The hook input data.
    """
    if hook.stop and hook.stop.stopHookActive:
        allow()

    result = collect_hook_results(
        load_plugins(),
        CanonicalHook.STOP,
        task_id=hook.taskId,
        workspace_roots=hook.workspaceRoots,
        agent_type=hook.agentType,
        transcript_path=hook.transcriptPath,
    )
    notes = list(result.notes)
    if result.block:
        notes.append(result.block)

    if not notes:
        allow()

    feedback("\n\n".join(notes))
