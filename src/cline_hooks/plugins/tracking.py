from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from cline_hooks.core.hook_kwargs import TrackToolUseKwargs
from cline_hooks.core.parameters import ReadParameters, ShellParameters, SkillParameters
from cline_hooks.core.plugin import HooksPlugin
from cline_hooks.core.vocabulary import SHELL_TOOLS, CanonicalTool, PluginScope
from cline_hooks.state.agents import is_agent_tool, record_agent_use
from cline_hooks.state.memory import is_memory_write, record_memory_write
from cline_hooks.state.skills import record_skill, skills_in_command

if TYPE_CHECKING:
    import logging

    from cline_hooks.core.plugin import HookResult


def _record_skill_use(task_id: str, tool_name: str, parameters: dict[str, Any]) -> None:
    """Record any skill loaded by a tool call.

    Skills load via the canonical skill tool, a read of a SKILL.md file, or a
    shell command that reads one.

    Args:
        task_id: The session or task identifier.
        tool_name: The tool name as reported by the frontend.
        parameters: The tool parameters.
    """
    if tool_name == CanonicalTool.SKILL:
        skill_name = str(SkillParameters.build(parameters).skill)
        if skill_name:
            record_skill(task_id, skill_name)
    elif tool_name == CanonicalTool.READ:
        path = ReadParameters.build(parameters).path
        if path:
            file_path = PurePosixPath(path)
            if file_path.name == "SKILL.md":
                record_skill(task_id, file_path.parent.name)
    elif tool_name in SHELL_TOOLS:
        for skill_name in skills_in_command(str(ShellParameters.build(parameters).command)):
            record_skill(task_id, skill_name)


class TrackingPlugin(HooksPlugin):
    """Records skill loads, memory writes, and agent-spawn tool use."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Record tool-use tracking state on the TrackToolUse scope.

        Args:
            hook_name: The hook event or plugin-scope name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            None; this plugin only records state, it never contributes notes.
        """
        if hook_name != PluginScope.TRACK_TOOL_USE:
            return None
        kw = TrackToolUseKwargs.build(kwargs)
        if kw.tool_name != CanonicalTool.MCP:
            _record_skill_use(kw.task_id, kw.tool_name, kw.parameters)
        if kw.mcp_tool_name is not None and is_memory_write(kw.mcp_tool_name):
            record_memory_write(kw.task_id, kw.mcp_tool_name)
        if is_agent_tool(kw.tool_name):
            record_agent_use(kw.task_id, kw.tool_name)
        return None
