from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from cline_hooks.core.outcome import Outcome
from cline_hooks.core.parameters import McpToolUse
from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.registry import TOOL_HANDLERS, hook_handler
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool, PluginScope
from cline_hooks.handlers.git_context import resolve_tooling_notes
from cline_hooks.plugins.research import record_research_use
from cline_hooks.state.workspace import should_note_workspace_change

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputPostToolUse
    from cline_hooks.core.plugin import HooksPlugin

logger = logging.getLogger("hooks.post_tool_use")


def _record_tool_use(task_id: str, tool_name: str, parameters: dict[str, Any]) -> str | None:
    """Record research use for a tool call and resolve its MCP identity.

    Args:
        task_id: The session or task identifier.
        tool_name: The tool name as reported by the frontend.
        parameters: The tool parameters.

    Returns:
        The MCP tool name, or None if this was not an MCP call.
    """
    mcp_tool_name: str | None = None
    arguments = parameters
    if tool_name == CanonicalTool.MCP:
        tool = McpToolUse.build(parameters)
        mcp_tool_name = tool.tool_name
        arguments = tool.arguments

    record_research_use(task_id, tool_name, mcp_tool_name, arguments)

    return mcp_tool_name


def _workspace_change_outcome(hook: HookInputPostToolUse, plugins: list[HooksPlugin]) -> Outcome:
    """Build the ecosystem tooling guidance outcome for a workspace root change.

    Args:
        hook: The hook input data.
        plugins: Loaded plugin instances.

    Returns:
        An ALLOW Outcome with the tooling note, or an empty Outcome if the
        working directory hasn't changed or there's no note to show.
    """
    if not should_note_workspace_change(hook.stateKey, hook.workspaceRoots):
        return Outcome()
    notes = resolve_tooling_notes(plugins, hook.workspaceRoots)
    if not notes:
        return Outcome()
    return Outcome.allow(
        f"Working directory changed to {hook.workspaceRoots[0]}. " + "\n\n".join(notes),
        label="REMINDER",
    )


@hook_handler(CanonicalHook.POST_TOOL_USE)
def handle_post_tool_use(hook: HookInputPostToolUse) -> Outcome:
    """Handle PostToolUse hook events.

    Args:
        hook: The hook input data.

    Returns:
        The merged Outcome for this tool call.
    """
    if hook.postToolUse is None:
        return Outcome()

    tool_name = hook.postToolUse.toolName
    parameters = hook.postToolUse.parameters

    logger.info("Called %s", tool_name)

    plugins = load_plugins()

    if not hook.postToolUse.success:
        logger.warning("Tool %s failed", tool_name)
        failure_result = collect_hook_results(
            plugins,
            PluginScope.TOOL_FAILED,
            task_id=hook.stateKey,
            tool_name=tool_name,
            parameters=parameters,
            workspace_roots=hook.workspaceRoots,
            agent_type=hook.agentType,
            agent_id=hook.agentId,
            is_teammate=hook.isTeammate,
            **hook.postToolUse.frontend_kwargs(),
        )
        return Outcome.allow("\n\n".join(failure_result.notes))

    mcp_tool_name = _record_tool_use(hook.stateKey, tool_name, parameters)

    track_result = collect_hook_results(
        plugins,
        PluginScope.TRACK_TOOL_USE,
        task_id=hook.stateKey,
        tool_name=tool_name,
        parameters=parameters,
        mcp_tool_name=mcp_tool_name,
        workspace_roots=hook.workspaceRoots,
        agent_type=hook.agentType,
        agent_id=hook.agentId,
        is_teammate=hook.isTeammate,
    )

    result = collect_hook_results(
        plugins,
        CanonicalHook.POST_TOOL_USE,
        task_id=hook.stateKey,
        tool_name=tool_name,
        parameters=hook.postToolUse.parameters,
        mcp_tool_name=mcp_tool_name,
        workspace_roots=hook.workspaceRoots,
        agent_type=hook.agentType,
        transcript_path=hook.transcriptPath,
        success=hook.postToolUse.success,
        tool_result=hook.postToolUse.result,
        agent_id=hook.agentId,
        is_teammate=hook.isTeammate,
        **hook.postToolUse.frontend_kwargs(),
    )

    outcome = Outcome()
    if track_result.notes:
        outcome = outcome.merge(Outcome.allow("\n\n".join(track_result.notes)))
    if result.notes:
        outcome = outcome.merge(Outcome.allow("\n\n".join(result.notes)))

    handler = TOOL_HANDLERS.get((CanonicalHook.POST_TOOL_USE, tool_name))
    if handler is not None:
        outcome = outcome.merge(handler(hook, hook.postToolUse, plugins))

    if not outcome.notes:
        outcome = outcome.merge(_workspace_change_outcome(hook, plugins))

    return outcome
