"""Canonical tool, hook, and task-source vocabulary shared across frontends."""

from __future__ import annotations

from enum import StrEnum


class CanonicalTool(StrEnum):
    """Frontend-agnostic tool identity that each frontend's parser maps its native names onto."""

    SHELL = "execute_command"
    READ = "read_file"
    EDIT = "replace_in_file"
    WRITE = "write_to_file"
    MCP = "use_mcp_tool"
    ATTEMPT_COMPLETION = "attempt_completion"
    PLAN_MODE_RESPOND = "plan_mode_respond"
    SKILL = "use_skill"
    SPAWN_AGENT = "spawn_agent"
    PLAN_EXIT = "exit_plan_mode"
    WEB_FETCH = "web_fetch"
    WEB_SEARCH = "web_search"


class CanonicalHook(StrEnum):
    """Frontend-agnostic hook event name."""

    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    TASK_START = "TaskStart"
    TASK_RESUME = "TaskResume"
    TASK_CANCEL = "TaskCancel"
    TASK_COMPLETE = "TaskComplete"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    PRE_COMPACT = "PreCompact"
    STOP = "Stop"


class PluginScope(StrEnum):
    """Plugin-dispatch scope name that is not a lifecycle hook event."""

    PRE_MCP_TOOL_USE = "PreMcpToolUse"
    ATTEMPT_COMPLETION = "AttemptCompletion"


class TaskSource(StrEnum):
    """Frontend-agnostic reason a task/session started or resumed."""

    STARTUP = "startup"
    RESUME = "resume"
    COMPACT = "compact"
    CLEAR = "clear"


SHELL_TOOLS = frozenset({CanonicalTool.SHELL})
FILE_EDIT_TOOLS = frozenset({CanonicalTool.EDIT, CanonicalTool.WRITE})
FILE_READ_TOOLS = frozenset({CanonicalTool.READ})
SKILL_TOOLS = frozenset({CanonicalTool.SKILL})
WEB_RESEARCH_TOOLS = frozenset({CanonicalTool.WEB_FETCH, CanonicalTool.WEB_SEARCH})
AGENT_SPAWN_TOOLS = frozenset({CanonicalTool.SPAWN_AGENT})
PLAN_EXIT_TOOLS = frozenset({CanonicalTool.PLAN_EXIT, CanonicalTool.PLAN_MODE_RESPOND})
KNOWN_TOOLS = frozenset(CanonicalTool)
