from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

import bashlex
import bashlex.errors
import git

import cline_hooks.memory_tracker as _memory_tracker
from cline_hooks.commands import (
    check_rules,
    contains_comment,
    extract_commands,
    extract_replacement_blocks,
    get_all_command_rules,
)
from cline_hooks.models import HookInputPreToolUse, McpToolUse
from cline_hooks.plugin import load_plugins
from cline_hooks.registry import hook_handler
from cline_hooks.response import allow, block
from cline_hooks.state import TaskStateStore
from cline_hooks.skill_tracker import (
    is_skill_called as _is_skill_called,
    required_skill_for,
)

logger = logging.getLogger("hooks")

_LARGE_FILE_THRESHOLD = 1000
_MEMORY_BLOCK_THRESHOLD = 10

_MEMORY_WRITE_TOOL_NAMES = {
    "create_entities",
    "create_relations",
    "add_observations",
    "delete_entity",
    "delete_relation",
    "delete_observations",
}


def _starts_with_emoji(text: str) -> bool:
    """Check if text starts with a non-ASCII character (emoji canary).

    Args:
        text: The text to check.

    Returns:
        True if the first non-whitespace character is non-ASCII.
    """
    stripped = text.lstrip()
    return bool(stripped) and ord(stripped[0]) > 0x7F


def _is_memory_write_mcp(tool_name: str, parameters: dict[str, object]) -> bool:
    """Return True if the tool call is a write to a memory MCP server.

    Args:
        tool_name: The outer tool name (must be use_mcp_tool).
        parameters: The tool parameters dict.

    Returns:
        True if this is a memory write operation.
    """
    if tool_name != "use_mcp_tool":
        return False
    try:
        inner = McpToolUse(**cast(dict[str, Any], parameters))
    except (TypeError, KeyError):
        return False
    return inner.tool_name in _MEMORY_WRITE_TOOL_NAMES


def _check_memory_block(
    task_id: str, tool_name: str, parameters: dict[str, object]
) -> None:
    """Block tool execution if memory has not been updated recently.

    Args:
        task_id: The Cline task identifier.
        tool_name: The tool being called.
        parameters: The tool parameters.
    """
    if _is_memory_write_mcp(tool_name, parameters):
        return
    if _memory_tracker.should_block(task_id, _MEMORY_BLOCK_THRESHOLD):
        block(
            f"Memory has not been updated in the last {_MEMORY_BLOCK_THRESHOLD} tool calls. "
            "Update memory now before continuing.",
            task_id=task_id,
            tool_name=tool_name,
        )


@hook_handler("PreToolUse")
def handle_pre_tool_use(hook: HookInputPreToolUse) -> None:  # noqa: C901, PLR0912
    """Handle PreToolUse hook events.

    Args:
        hook: The hook input data.
    """
    if hook.preToolUse is None:
        return

    tool_name = hook.preToolUse.toolName
    parameters = hook.preToolUse.parameters

    if tool_name not in (
        "execute_command",
        "plan_mode_respond",
        "read_file",
        "replace_in_file",
        "use_mcp_tool",
        "attempt_completion",
    ):
        logger.debug("Ignoring unhandled tool: %s", tool_name)
        return

    logger.info("Called %s", tool_name)

    TaskStateStore().clear_blocks(hook.taskId)

    _check_memory_block(hook.taskId, tool_name, parameters)

    if tool_name == "plan_mode_respond":
        response: str = parameters.get("response", "")
        if not _starts_with_emoji(response):
            block(
                "Response does not start with an emoji - context window may be degraded. "
                "Use the new_task tool to start a fresh context.",
                task_id=hook.taskId,
                tool_name=tool_name,
            )

    elif tool_name == "read_file":
        path: str = parameters.get("path", "")
        if path:
            try:
                line_count = (
                    Path(path).read_text(encoding="utf-8", errors="replace").count("\n")
                )
                if line_count > _LARGE_FILE_THRESHOLD:
                    block(
                        f"{path} is {line_count} lines. Use a tool such as search_files with specific patterns instead of reading the whole file.",
                        task_id=hook.taskId,
                        tool_name=tool_name,
                    )
            except OSError:
                pass

    elif tool_name == "execute_command":
        command: str = parameters.get("command", "")
        if not command:
            return

        try:
            parsed = bashlex.parse(command)
        except bashlex.errors.ParsingError:
            logger.exception("Failed to parse command: %s", command)
            return

        violated_rule = check_rules(
            extract_commands(parsed), get_all_command_rules(load_plugins())
        )
        if violated_rule:
            block(violated_rule.message, task_id=hook.taskId, tool_name=tool_name)

        required_skill = required_skill_for(
            [cmd.name for cmd in extract_commands(parsed)]
        )
        if required_skill and not _is_skill_called(hook.taskId, required_skill):
            block(
                f"Use the `{required_skill}` skill before running this command",
                task_id=hook.taskId,
                tool_name=tool_name,
            )

    elif tool_name == "replace_in_file":
        diff = parameters.get("diff", "")
        if not diff:
            return

        replacement_blocks = extract_replacement_blocks(diff)
        logger.debug("block count: %s", len(replacement_blocks))

        notes: set[str] = set()

        for replacement_block in replacement_blocks:
            for line in replacement_block.split("\n"):
                if (stripped_line := line.strip()) and contains_comment(line):
                    logger.debug("comment in line: %s", stripped_line)
                    if (
                        "# type: ignore" in stripped_line
                        and "ignore[" not in stripped_line
                    ):
                        notes.add(
                            "Avoid using type ignore comments where possible. If necessary, use specific ignores."
                        )
                    else:
                        notes.add(
                            "It is extremely important that you NEVER write comments explaining the "
                            "reasoning for a specific change. Comments should only be used to explain "
                            "complex code. If comments are required, consider a different approach."
                        )

        if notes:
            allow("\n\n".join(notes))

    elif tool_name == "use_mcp_tool":
        tool = McpToolUse(**parameters)
        for plugin in load_plugins():
            reason = plugin.validate_mcp_tool(tool.tool_name, tool.arguments)
            if reason:
                block(reason, task_id=hook.taskId, tool_name=tool_name)

    elif tool_name == "attempt_completion":
        task_progress: str = parameters.get("task_progress", "") or ""
        incomplete = [
            line
            for line in task_progress.splitlines()
            if line.strip().startswith("- [ ]")
        ]
        if incomplete:
            block(
                f"task_progress has {len(incomplete)} incomplete item(s). Complete them before finishing.",
                task_id=hook.taskId,
                tool_name=tool_name,
            )

        allow(
            "REQUIRED before completing:\n"
            "1. Update `memory-project` and `memory-global`\n"
            "2. One observation per fact (what changed, why, TODOs)",
            prefix="IMPORTANT",
        )
        try:
            repo = git.Repo(".")
            if repo.is_dirty():
                block(
                    "Working directory has uncommitted changes",
                    task_id=hook.taskId,
                    tool_name=tool_name,
                )
        except git.InvalidGitRepositoryError:
            pass
