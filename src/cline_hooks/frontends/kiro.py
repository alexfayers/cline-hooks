"""Kiro frontend: exit-code protocol, input parsing, tool name mapping, and installation."""
# ruff: noqa: T201
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any, NoReturn, cast

from cline_hooks.models import (
    HookInput,
    HookInputPostToolUse,
    HookInputPreToolUse,
    HookInputTaskStart,
    HookInputUserPromptSubmit,
    PostToolUseFields,
    PreToolUseFields,
    TaskStartFields,
    UserPromptSubmitFields,
    _filter_fields,
)
from cline_hooks.protocol import Protocol

_KIRO_HOOK_MAP: dict[str, str] = {
    "preToolUse": "PreToolUse",
    "postToolUse": "PostToolUse",
    "agentSpawn": "TaskStart",
    "userPromptSubmit": "UserPromptSubmit",
    "stop": "Stop",
}

_KIRO_TOOL_MAP: dict[str, str] = {
    "execute_bash": "execute_command",
    "fs_read": "read_file",
    "fs_write": "replace_in_file",
    "use_aws": "execute_command",
}


class KiroProtocol(Protocol):
    """Kiro exit-code protocol: exit 0 + stdout for allow, exit 2 + stderr for block."""

    def allow(self, message: str | None = None) -> NoReturn:
        """Allow via exit 0, context on stdout."""
        if message is not None:
            print(message, end="")
        sys.exit(0)

    def block(self, message: str) -> NoReturn:
        """Block via exit 2, error on stderr."""
        print(message, end="", file=sys.stderr)
        sys.exit(2)


def _map_tool_name(kiro_name: str) -> str:
    """Map a Kiro tool name to its Cline equivalent.

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

    session_id = hashlib.sha256(cwd.encode()).hexdigest()[:16] if cwd else ""

    base_fields: dict[str, Any] = {
        "taskId": session_id,
        "workspaceRoots": [cwd] if cwd else [],
        "hookName": canonical_hook,
    }

    tool_name_raw = data.get("tool_name", "")
    tool_input: dict[str, Any] = data.get("tool_input", {})
    tool_name = _map_tool_name(tool_name_raw) if tool_name_raw else ""

    if canonical_hook == "PreToolUse" and tool_name:
        params = _build_mcp_parameters(tool_name_raw, tool_input) if tool_name_raw.startswith("@") else tool_input
        base_fields["preToolUse"] = PreToolUseFields(toolName=tool_name, parameters=params)
        return HookInputPreToolUse(**_filter_fields(HookInputPreToolUse, base_fields))

    if canonical_hook == "PostToolUse" and tool_name:
        params = _build_mcp_parameters(tool_name_raw, tool_input) if tool_name_raw.startswith("@") else tool_input
        tool_response = data.get("tool_response", {})
        base_fields["postToolUse"] = PostToolUseFields(
            toolName=tool_name,
            parameters=params,
            success=tool_response.get("success", True),
            executionTimeMs=0,
            result=cast("str | None", tool_response.get("result")),
        )
        return HookInputPostToolUse(**_filter_fields(HookInputPostToolUse, base_fields))

    if canonical_hook == "TaskStart":
        base_fields["taskStart"] = TaskStartFields()
        return HookInputTaskStart(**_filter_fields(HookInputTaskStart, base_fields))

    if canonical_hook == "UserPromptSubmit":
        base_fields["userPromptSubmit"] = UserPromptSubmitFields(
            userMessage=data.get("prompt", ""),
        )
        return HookInputUserPromptSubmit(**_filter_fields(HookInputUserPromptSubmit, base_fields))

    return HookInput(**_filter_fields(HookInput, base_fields))


# -- Installation -------------------------------------------------------------

_KIRO_HOOKS: dict[str, str | None] = {
    "agentSpawn": None,
    "userPromptSubmit": None,
    "preToolUse": "*",
    "postToolUse": "*",
    "stop": None,
}


def _build_kiro_hooks(binary: Path) -> dict[str, list[dict[str, str]]]:
    """Build the hooks section for a Kiro agent config.

    Args:
        binary: Path to the cline-hook binary.

    Returns:
        A dict suitable for the "hooks" key in a Kiro agent JSON.
    """
    hooks: dict[str, list[dict[str, str]]] = {}
    for hook_name, matcher in _KIRO_HOOKS.items():
        entry: dict[str, str] = {
            "command": str(binary),
            "description": f"cline-hooks {hook_name}",
        }
        if matcher is not None:
            entry["matcher"] = matcher
        hooks[hook_name] = [entry]
    return hooks


def install_kiro(agent_config_path: str) -> None:
    """Patch a Kiro agent config JSON file with cline-hooks entries.

    Args:
        agent_config_path: Path to the agent JSON file to patch.
    """
    from cline_hooks.install import resolve_binary  # noqa: PLC0415

    binary = resolve_binary()
    config_path = Path(agent_config_path)

    if not config_path.exists():
        print(f"error: {config_path} does not exist", file=sys.stderr)
        sys.exit(1)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["hooks"] = _build_kiro_hooks(binary)
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"Patched {config_path} with {len(_KIRO_HOOKS)} hooks.")
