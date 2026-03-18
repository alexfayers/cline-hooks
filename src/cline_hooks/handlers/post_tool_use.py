from __future__ import annotations

import logging
import random
from dataclasses import asdict

import cline_hooks.memory_tracker as _memory_tracker
from cline_hooks.models import HookInputPostToolUse, McpToolUse
from cline_hooks.registry import hook_handler
from cline_hooks.response import allow
from cline_hooks.skill_tracker import record_skill as _record_skill

logger = logging.getLogger("hooks")

_MEMORY_REMINDER = (
    "MEMORY UPDATE REQUIRED: Update both memory servers (project and global) now.\n"
    "Record what you just did and why. One fact per observation."
)
_MEMORY_REMINDER_CHANCE = 0.6
_MEMORY_COOLDOWN_STEPS = 5

_MEMORY_TOOL_NAMES = {
    "create_entities",
    "create_relations",
    "read_graph",
    "search_nodes",
    "get_entity_with_relations",
    "delete_entity",
    "delete_relation",
}

_MEMORY_WRITE_TOOL_NAMES = {
    "create_entities",
    "create_relations",
    "add_observations",
    "delete_entity",
    "delete_relation",
    "delete_observations",
}

_current_memory_chance = _MEMORY_REMINDER_CHANCE


def _step_memory_chance() -> None:
    global _current_memory_chance  # noqa: PLW0603
    increment = _MEMORY_REMINDER_CHANCE / _MEMORY_COOLDOWN_STEPS
    _current_memory_chance = min(
        _MEMORY_REMINDER_CHANCE, _current_memory_chance + increment
    )


def _reset_memory_chance() -> None:
    global _current_memory_chance  # noqa: PLW0603
    _current_memory_chance = 0.0


def handle_post_mcp_tool_use(tool: McpToolUse, task_id: str) -> None:
    """Handle post-MCP tool usage.

    Args:
        tool: The MCP tool invocation that completed.
        task_id: The Cline task identifier.
    """
    logger.debug("Post MCP tool usage: %s", asdict(tool))
    if tool.tool_name in _MEMORY_WRITE_TOOL_NAMES:
        _memory_tracker.reset(task_id)
    if tool.tool_name in _MEMORY_TOOL_NAMES:
        _reset_memory_chance()


@hook_handler("PostToolUse")
def handle_post_tool_use(hook: HookInputPostToolUse) -> None:
    """Handle PostToolUse hook events.

    Args:
        hook: The hook input data.
    """
    if hook.postToolUse is None:
        return

    tool_name = hook.postToolUse.toolName
    parameters = hook.postToolUse.parameters

    logger.info("Called %s", tool_name)

    _memory_tracker.increment(hook.taskId)

    if not hook.postToolUse.success:
        logger.warning("Tool %s failed", tool_name)
        return

    if tool_name in {
        "replace_in_file",
        "write_to_file",
        "execute_command",
        "plan_mode_respond",
    }:
        _step_memory_chance()
        notes: list[str] = []
        if random.random() < _current_memory_chance:  # noqa: S311
            notes.append(_MEMORY_REMINDER)
            _reset_memory_chance()
        if notes:
            allow("\n\n".join(notes), prefix="")

    if tool_name == "execute_command":
        result = hook.postToolUse.result
        if result and "BUILD FAILED" in result:
            allow("The build failed! It did NOT pass. It FAILED!!", prefix="")

    elif tool_name == "use_skill":
        skill_name = parameters.get("skill_name", "")
        if skill_name:
            _record_skill(hook.taskId, str(skill_name))

    elif tool_name == "use_mcp_tool":
        handle_post_mcp_tool_use(McpToolUse(**parameters), hook.taskId)
