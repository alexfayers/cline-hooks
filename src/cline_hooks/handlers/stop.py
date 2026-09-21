from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.core.outcome import Outcome
from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.registry import hook_handler
from cline_hooks.core.vocabulary import CanonicalHook
from cline_hooks.state.agents import reset as _reset_agents
from cline_hooks.state.memory import reset as _reset_memory
from cline_hooks.state.skills import reset as _reset_skills
from cline_hooks.state.store import TaskStateStore
from cline_hooks.state.workspace import reset as reset_workspace

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInput, HookInputStop, HookInputSubagentStop, StopFields


def _discard_agent_state(state_key: str) -> None:
    """Clear a finished subagent's own per-agent hook state.

    Args:
        state_key: The subagent's per-agent state key.
    """
    _reset_skills(state_key)
    _reset_memory(state_key)
    _reset_agents(state_key)
    reset_workspace(state_key)
    TaskStateStore().clear_blocks(state_key, discard_children=False)


def _dispatch_stop(hook: HookInput, canonical_hook: CanonicalHook, stop_fields: StopFields | None) -> Outcome:
    """Dispatch a Stop-shaped hook (main or subagent) to plugins.

    Args:
        hook: The hook input data.
        canonical_hook: The canonical hook to dispatch as.
        stop_fields: The hook's own StopFields payload, if present.

    Returns:
        The merged Outcome for this stop event.
    """
    discards_agent_state = canonical_hook is CanonicalHook.SUBAGENT_STOP and bool(hook.agentId)
    if stop_fields and stop_fields.stopHookActive:
        if discards_agent_state:
            _discard_agent_state(hook.stateKey)
        return Outcome.allow()

    result = collect_hook_results(
        load_plugins(),
        canonical_hook,
        task_id=hook.stateKey,
        workspace_roots=hook.workspaceRoots,
        agent_type=hook.agentType,
        transcript_path=hook.transcriptPath,
        agent_id=hook.agentId,
        is_teammate=hook.isTeammate,
    )
    notes = list(result.notes)
    if result.block:
        notes.append(result.block)

    if not notes:
        if discards_agent_state:
            _discard_agent_state(hook.stateKey)
        return Outcome.allow()

    return Outcome.feedback("\n\n".join(notes))


@hook_handler(CanonicalHook.STOP)
def handle_stop(hook: HookInputStop) -> Outcome:
    """Handle Stop hook events by dispatching to plugins.

    Args:
        hook: The hook input data.

    Returns:
        The merged Outcome for this stop event.
    """
    return _dispatch_stop(hook, CanonicalHook.STOP, hook.stop)


@hook_handler(CanonicalHook.SUBAGENT_STOP)
def handle_subagent_stop(hook: HookInputSubagentStop) -> Outcome:
    """Handle SubagentStop hook events by dispatching to plugins.

    Args:
        hook: The hook input data.

    Returns:
        The merged Outcome for this subagent stop event.
    """
    return _dispatch_stop(hook, CanonicalHook.SUBAGENT_STOP, hook.subagentStop)
