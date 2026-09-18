from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import bashlex
import bashlex.errors

from cline_hooks.core.outcome import Disposition, Outcome
from cline_hooks.core.parameters import (
    AttemptCompletionParameters,
    McpToolUse,
    ShellParameters,
)
from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.registry import TOOL_HANDLERS, hook_handler, tool_handler
from cline_hooks.core.vocabulary import (
    KNOWN_TOOLS,
    SHELL_TOOLS,
    CanonicalHook,
    CanonicalTool,
    PluginScope,
)
from cline_hooks.handlers.commands import (
    check_rules,
    extract_commands,
    get_all_command_rules,
)
from cline_hooks.state.store import TaskStateStore

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputPreToolUse, PreToolUseFields
    from cline_hooks.core.plugin import HooksPlugin

logger = logging.getLogger("hooks.pre_tool_use")


def _hook_result_outcome(
    hook_name: str,
    plugins: list[HooksPlugin],
    task_id: str,
    tool_name: str,
    **kwargs: object,
) -> Outcome:
    """Collect plugin results as an Outcome.

    Args:
        hook_name: The hook or plugin-scope name.
        plugins: Loaded plugin instances.
        task_id: The task identifier.
        tool_name: The tool being validated.
        **kwargs: Additional kwargs passed to on_hook.

    Returns:
        A BLOCK Outcome for a plugin block, an ALLOW Outcome carrying plugin
        notes, otherwise an empty Outcome.
    """
    result = collect_hook_results(plugins, hook_name, task_id=task_id, tool_name=tool_name, **kwargs)
    if result.block:
        return Outcome.block(result.block)
    if result.notes:
        return Outcome.allow("\n\n".join(result.notes), label="REMINDER")
    return Outcome()


@tool_handler(CanonicalHook.PRE_TOOL_USE, *SHELL_TOOLS)
def _pre_shell(hook: HookInputPreToolUse, fields: PreToolUseFields, plugins: list[HooksPlugin]) -> Outcome:
    """Enforce command rules and dispatch to plugins' shell guards.

    Args:
        hook: The hook input data.
        fields: The PreToolUse fields.
        plugins: Loaded plugin instances.

    Returns:
        A BLOCK Outcome for a violated command rule, otherwise the
        plugin-derived Outcome.
    """
    command: str = ShellParameters.build(fields.parameters).command
    if not command:
        return Outcome()

    try:
        parsed = bashlex.parse(command)
    except bashlex.errors.ParsingError:
        logger.debug("Failed to parse command (unsupported shell syntax): %s", command)
        return Outcome()

    commands = extract_commands(parsed)

    violated_rule = check_rules(commands, get_all_command_rules(plugins))
    if violated_rule:
        return Outcome.block(violated_rule.message)

    return _hook_result_outcome(
        PluginScope.PRE_SHELL,
        plugins,
        hook.taskId,
        fields.toolName,
        command=command,
        workspace_roots=hook.workspaceRoots,
        agent_type=hook.agentType,
    )


@tool_handler(CanonicalHook.PRE_TOOL_USE, CanonicalTool.MCP)
def _pre_mcp(hook: HookInputPreToolUse, fields: PreToolUseFields, plugins: list[HooksPlugin]) -> Outcome:
    """Dispatch a use_mcp_tool call to plugins' PreMcpToolUse handling.

    Args:
        hook: The hook input data.
        fields: The PreToolUse fields.
        plugins: Loaded plugin instances.

    Returns:
        The plugin-derived Outcome for this MCP tool call.
    """
    tool = McpToolUse.build(fields.parameters)
    return _hook_result_outcome(
        PluginScope.PRE_MCP_TOOL_USE,
        plugins,
        hook.taskId,
        fields.toolName,
        mcp_tool_name=tool.tool_name,
        mcp_arguments=tool.arguments,
        agent_type=hook.agentType,
    )


@tool_handler(CanonicalHook.PRE_TOOL_USE, CanonicalTool.ATTEMPT_COMPLETION)
def _pre_attempt_completion(hook: HookInputPreToolUse, fields: PreToolUseFields, plugins: list[HooksPlugin]) -> Outcome:
    """Dispatch attempt_completion validation to plugins.

    Args:
        hook: The hook input data.
        fields: The PreToolUse fields.
        plugins: Loaded plugin instances.

    Returns:
        A BLOCK Outcome for a plugin block, an ALLOW Outcome carrying plugin
        notes, otherwise an empty Outcome.
    """
    task_progress: str = AttemptCompletionParameters.build(fields.parameters).task_progress or ""
    result = collect_hook_results(
        plugins,
        PluginScope.ATTEMPT_COMPLETION,
        task_id=hook.taskId,
        workspace_roots=hook.workspaceRoots,
        task_progress=task_progress,
    )
    if result.block:
        return Outcome.block(result.block)
    if result.notes:
        return Outcome.allow("\n\n".join(result.notes), label="IMPORTANT")
    return Outcome()


@hook_handler(CanonicalHook.PRE_TOOL_USE)
def handle_pre_tool_use(hook: HookInputPreToolUse) -> Outcome:
    """Handle PreToolUse hook events.

    Args:
        hook: The hook input data.

    Returns:
        The merged Outcome for this tool call.
    """
    if hook.preToolUse is None:
        return Outcome()

    tool_name = hook.preToolUse.toolName

    if tool_name not in KNOWN_TOOLS:
        logger.debug("Ignoring unhandled tool: %s", tool_name)
        return Outcome()

    logger.info("Called %s", tool_name)

    TaskStateStore().clear_blocks(hook.taskId)

    plugins = load_plugins()
    outcome = _hook_result_outcome(
        CanonicalHook.PRE_TOOL_USE,
        plugins,
        hook.taskId,
        tool_name,
        parameters=hook.preToolUse.parameters,
        workspace_roots=hook.workspaceRoots,
        agent_type=hook.agentType,
    )

    handler = TOOL_HANDLERS.get((CanonicalHook.PRE_TOOL_USE, tool_name))
    if handler is not None:
        outcome = outcome.merge(handler(hook, hook.preToolUse, plugins))

    if outcome.disposition is Disposition.BLOCK:
        TaskStateStore().record_block(hook.taskId, tool_name, outcome.message or "")

    return outcome
