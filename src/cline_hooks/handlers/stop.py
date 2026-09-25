from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.registry import hook_handler
from cline_hooks.core.response import allow, feedback
from cline_hooks.core.vocabulary import CanonicalHook

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInput, HookInputStop, HookInputSubagentStop, StopFields


def _dispatch_stop(hook: HookInput, canonical_hook: CanonicalHook, stop_fields: StopFields | None) -> None:
    """Dispatch a Stop-shaped hook (main or subagent) to plugins.

    Args:
        hook: The hook input data.
        canonical_hook: The canonical hook to dispatch as.
        stop_fields: The hook's own StopFields payload, if present.
    """
    if stop_fields and stop_fields.stopHookActive:
        allow()

    result = collect_hook_results(
        load_plugins(),
        canonical_hook,
        task_id=hook.stateKey,
        workspace_roots=hook.workspaceRoots,
        agent_type=hook.agentType,
        transcript_path=hook.transcriptPath,
        agent_id=hook.agentId,
    )
    notes = list(result.notes)
    if result.block:
        notes.append(result.block)

    if not notes:
        allow()

    feedback("\n\n".join(notes))


@hook_handler(CanonicalHook.STOP)
def handle_stop(hook: HookInputStop) -> None:
    """Handle Stop hook events by dispatching to plugins.

    Args:
        hook: The hook input data.
    """
    _dispatch_stop(hook, CanonicalHook.STOP, hook.stop)


@hook_handler(CanonicalHook.SUBAGENT_STOP)
def handle_subagent_stop(hook: HookInputSubagentStop) -> None:
    """Handle SubagentStop hook events by dispatching to plugins.

    Args:
        hook: The hook input data.
    """
    _dispatch_stop(hook, CanonicalHook.SUBAGENT_STOP, hook.subagentStop)
