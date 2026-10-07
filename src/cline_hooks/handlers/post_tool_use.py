from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from cline_hooks.core.outcome import Outcome
from cline_hooks.core.parameters import McpToolUse
from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.registry import TOOL_HANDLERS, hook_handler
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool, PluginScope
from cline_hooks.plugins.research import record_research_use

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputPostToolUse

logger = logging.getLogger("hooks.post_tool_use")


def _record_tool_use(task_id: str, tool_name: str, parameters: dict[str, Any], agent: str = "") -> str | None:
    """Record research use for a tool call and resolve its MCP identity.

    Args:
        task_id: The session or task identifier.
        tool_name: The tool name as reported by the frontend.
        parameters: The tool parameters.
        agent: The label of the subagent making the call, empty for the main agent.

    Returns:
        The MCP tool name, or None if this was not an MCP call.
    """
    mcp_tool_name: str | None = None
    arguments = parameters
    if tool_name == CanonicalTool.MCP:
        tool = McpToolUse.build(parameters)
        mcp_tool_name = tool.tool_name
        arguments = tool.arguments

    record_research_use(task_id, tool_name, mcp_tool_name, arguments, agent)

    return mcp_tool_name


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

    agent_label = (f"{hook.agentType}/{hook.agentId}" if hook.agentType else hook.agentId) if hook.agentId else ""
    mcp_tool_name = _record_tool_use(hook.stateKey, tool_name, parameters, agent_label)

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

    return outcome
