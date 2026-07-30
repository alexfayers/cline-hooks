"""Kiro input parser and tool name mapping."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, cast

from cline_hooks.core.models import (
    HookInput,
    HookInputPostToolUse,
    HookInputPreToolUse,
    HookInputStop,
    HookInputTaskStart,
    HookInputUserPromptSubmit,
    PostToolUseFields,
    PreToolUseFields,
    StopFields,
    TaskStartFields,
    UserPromptSubmitFields,
    _filter_fields,
)

_KIRO_HOOK_MAP: dict[str, str] = {
    "preToolUse": "PreToolUse",
    "postToolUse": "PostToolUse",
    "agentSpawn": "TaskStart",
    "userPromptSubmit": "UserPromptSubmit",
    "stop": "Stop",
    "SessionStart": "TaskStart",
}

_KIRO_TOOL_MAP: dict[str, str] = {
    "shell": "execute_command",
    "execute_bash": "execute_command",
    "read": "read_file",
    "fs_read": "read_file",
    "write": "replace_in_file",
    "fs_write": "replace_in_file",
    "grep": "read_file",
    "use_aws": "execute_command",
    "call_aws": "execute_command",
}


def _map_tool_name(kiro_name: str) -> str:
    """Map a Kiro tool name to its canonical equivalent.

    Args:
        kiro_name: The tool name from Kiro's hook event.

    Returns:
        The canonical tool name used by handlers.
    """
    if kiro_name.startswith("@"):
        return "use_mcp_tool"
    return _KIRO_TOOL_MAP.get(kiro_name, kiro_name)


def _build_mcp_parameters(kiro_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Build use_mcp_tool-style parameters from a Kiro @server/tool call.

    Args:
        kiro_name: The Kiro tool name in @server/tool format.
        tool_input: The tool input from the Kiro hook event.

    Returns:
        Parameters dict matching the use_mcp_tool schema.
    """
    parts = kiro_name.lstrip("@").split("/", 1)
    server_name = parts[0]
    tool_name = parts[1] if len(parts) > 1 else ""
    return {
        "server_name": server_name,
        "tool_name": tool_name,
        "arguments": json.dumps(tool_input),
    }


def _ensure_dict(value: dict[str, Any] | str | list[Any] | None) -> dict[str, Any]:
    """Normalise a value that should be a dict.

    Args:
        value: The raw value (may be dict, str, list, or None).

    Returns:
        A dict, falling back to {} for non-dict types.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


def _normalise_parameters(canonical_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Normalise Kiro tool parameters to match canonical handler expectations.

    Args:
        canonical_name: The mapped canonical tool name.
        tool_input: The raw tool input from Kiro.

    Returns:
        Parameters dict matching the canonical tool's expected shape.
    """
    if canonical_name == "read_file":
        operations: list[dict[str, Any]] = tool_input.get("operations", [])
        if operations:
            return {"path": operations[0].get("path", "")}
        return {}

    if canonical_name == "replace_in_file":
        result: dict[str, Any] = {}
        path = tool_input.get("path", "")
        if path:
            result["path"] = path
        new_content = tool_input.get("newStr", "") or tool_input.get("content", "")
        if new_content:
            result["diff"] = f"------- SEARCH\n=======\n{new_content}\n+++++++ REPLACE"
        return result

    return tool_input


def parse_kiro_data(raw_data: str) -> HookInput:
    """Parse raw JSON from Kiro into a typed HookInput subclass.

    Args:
        raw_data: The raw JSON string from Kiro.

    Returns:
        The most specific matching HookInput subclass.
    """
    data: dict[str, Any] = json.loads(raw_data)
    kiro_hook = data.get("hook_event_name", "")
    canonical_hook = _KIRO_HOOK_MAP.get(kiro_hook, kiro_hook)
    cwd = data.get("cwd", "")
    source = data.get("source", "")

    session_id = (
        data.get("session_id")
        or os.environ.get("KIRO_SESSION_ID")
        or (hashlib.sha256(cwd.encode()).hexdigest()[:16] if cwd else "")
    )

    base_fields: dict[str, Any] = {
        "taskId": session_id,
        "workspaceRoots": [cwd] if cwd else [],
        "hookName": canonical_hook,
        "transcriptPath": data.get("transcript_path", ""),
        "agentType": data.get("agent_type", ""),
    }

    tool_name_raw = data.get("tool_name", "")
    tool_input: dict[str, Any] = _ensure_dict(data.get("tool_input", {}))
    tool_name = _map_tool_name(tool_name_raw) if tool_name_raw else ""

    if canonical_hook == "PreToolUse" and tool_name:
        if tool_name_raw.startswith("@"):
            params = _build_mcp_parameters(tool_name_raw, tool_input)
        else:
            params = _normalise_parameters(tool_name, tool_input)
        base_fields["preToolUse"] = PreToolUseFields(toolName=tool_name, parameters=params)
        return HookInputPreToolUse(**_filter_fields(HookInputPreToolUse, base_fields))

    if canonical_hook == "PostToolUse" and tool_name:
        if tool_name_raw.startswith("@"):
            params = _build_mcp_parameters(tool_name_raw, tool_input)
        else:
            params = _normalise_parameters(tool_name, tool_input)
        tool_response = _ensure_dict(data.get("tool_response", {}))
        base_fields["postToolUse"] = PostToolUseFields(
            toolName=tool_name,
            parameters=params,
            success=tool_response.get("success", True),
            executionTimeMs=0,
            result=cast("str | None", tool_response.get("result")),
        )
        return HookInputPostToolUse(**_filter_fields(HookInputPostToolUse, base_fields))

    if canonical_hook == "TaskStart":
        base_fields["taskStart"] = TaskStartFields(source=source)
        return HookInputTaskStart(**_filter_fields(HookInputTaskStart, base_fields))

    if canonical_hook == "UserPromptSubmit":
        base_fields["userPromptSubmit"] = UserPromptSubmitFields(
            userMessage=data.get("prompt", ""),
        )
        return HookInputUserPromptSubmit(**_filter_fields(HookInputUserPromptSubmit, base_fields))

    if canonical_hook == "Stop":
        base_fields["stop"] = StopFields(stopHookActive=bool(data.get("stop_hook_active")))
        return HookInputStop(**_filter_fields(HookInputStop, base_fields))

    return HookInput(**_filter_fields(HookInput, base_fields))
