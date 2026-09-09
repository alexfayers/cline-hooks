"""Antigravity input parser and tool name mapping."""

from __future__ import annotations

import json
from typing import Any

from cline_hooks.core.models import (
    HookInput,
    HookInputPostToolUse,
    HookInputPreToolUse,
    HookInputStop,
    PostToolUseFields,
    PreToolUseFields,
    StopFields,
    _filter_fields,
    extract_mcp_tool_name,
)

_ANTIGRAVITY_TOOL_MAP: dict[str, str] = {
    "run_command": "execute_command",
    "view_file": "read_file",
    "write_to_file": "write_to_file",
    "replace_file_content": "replace_in_file",
}


def _clean_arg(val: Any) -> Any:
    """Strip redundant outer quotes from string values if present."""
    if isinstance(val, str) and len(val) >= 2 and val.startswith('"') and val.endswith('"'):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, ValueError):
            return val[1:-1]
    return val


def _normalise_args(args: dict[str, Any]) -> dict[str, Any]:
    """Clean all arguments in args dict."""
    return {k: _clean_arg(v) for k, v in args.items()}


def _map_tool_and_params(raw_name: str, raw_args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Map Antigravity tool name and arguments to canonical name and parameter dict."""
    canonical_name = _ANTIGRAVITY_TOOL_MAP.get(raw_name)
    if canonical_name == "execute_command":
        params = {
            "command": raw_args.get("CommandLine", ""),
            "cwd": raw_args.get("Cwd", ""),
        }
    elif canonical_name == "read_file":
        params = {
            "path": raw_args.get("AbsolutePath", ""),
            "StartLine": raw_args.get("StartLine"),
            "EndLine": raw_args.get("EndLine"),
        }
    elif canonical_name == "write_to_file":
        params = {
            "path": raw_args.get("TargetFile", ""),
            "content": raw_args.get("CodeContent", ""),
        }
    elif canonical_name == "replace_in_file":
        params = {
            "path": raw_args.get("TargetFile", ""),
            "diff": raw_args.get("ReplacementContent", ""),
        }
    else:
        canonical_name = extract_mcp_tool_name(raw_name)
        params = raw_args
    return canonical_name, params


def _find_tool_call_from_transcript(
    transcript_path: str, step_idx: int | None = None
) -> tuple[str, dict[str, Any]]:
    """Recover tool call name and arguments from transcript.jsonl."""
    if not transcript_path:
        return "", {}
    try:
        entries: list[dict[str, Any]] = []
        with open(transcript_path, encoding="utf-8") as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue
        if not entries:
            return "", {}
        candidates = [
            e
            for e in entries
            if e.get("type") == "PLANNER_RESPONSE" and e.get("tool_calls")
        ]
        if not candidates:
            return "", {}
        if step_idx is not None:
            matching = [
                e
                for e in candidates
                if e.get("step_index") == step_idx
                or (
                    isinstance(e.get("step_index"), int)
                    and e.get("step_index") <= step_idx
                )
            ]
            target = matching[-1] if matching else candidates[-1]
        else:
            target = candidates[-1]
        tool_calls = target.get("tool_calls", [])
        if tool_calls:
            tc = tool_calls[0]
            return str(tc.get("name", "")), _normalise_args(tc.get("args", {}))
    except Exception:
        pass
    return "", {}


def parse_antigravity_data(raw_data: str, event_override: str | None = None) -> HookInput:
    """Parse raw JSON from Antigravity into a typed HookInput subclass.

    Args:
        raw_data: The raw JSON string from stdin.
        event_override: Optional explicit event name ("PreToolUse", "PostToolUse", "Stop").

    Returns:
        The matching HookInput subclass.
    """
    data: dict[str, Any] = json.loads(raw_data)
    task_id = str(data.get("conversationId", ""))
    workspace_roots = data.get("workspacePaths", [])
    if isinstance(workspace_roots, str):
        workspace_roots = [workspace_roots]
    transcript_path = str(data.get("transcriptPath", ""))

    base_fields: dict[str, Any] = {
        "taskId": task_id,
        "workspaceRoots": workspace_roots,
        "transcriptPath": transcript_path,
        "agentType": str(data.get("modelName", "")),
    }

    event = event_override
    if not event:
        if "toolCall" in data:
            event = "PreToolUse"
        elif "executionNum" in data or "terminationReason" in data:
            event = "Stop"
        elif "stepIdx" in data:
            event = "PostToolUse"
        else:
            event = "PreToolUse"

    base_fields["hookName"] = event

    if event == "PreToolUse":
        tool_call = data.get("toolCall", {})
        raw_name = str(tool_call.get("name", ""))
        raw_args = _normalise_args(tool_call.get("args", {}))

        canonical_name, params = _map_tool_and_params(raw_name, raw_args)

        base_fields["preToolUse"] = PreToolUseFields(toolName=canonical_name, parameters=params)
        return HookInputPreToolUse(**_filter_fields(HookInputPreToolUse, base_fields))

    if event == "PostToolUse":
        tool_call = data.get("toolCall")
        if isinstance(tool_call, dict) and tool_call.get("name"):
            raw_name = str(tool_call.get("name", ""))
            raw_args = _normalise_args(tool_call.get("args", {}))
        else:
            step_idx = data.get("stepIdx")
            raw_name, raw_args = _find_tool_call_from_transcript(transcript_path, step_idx)

        canonical_name, params = _map_tool_and_params(raw_name, raw_args)

        error = data.get("error")
        base_fields["postToolUse"] = PostToolUseFields(
            toolName=canonical_name,
            parameters=params,
            success=error is None or error == "",
            executionTimeMs=0,
            result=str(error) if error else None,
        )
        return HookInputPostToolUse(**_filter_fields(HookInputPostToolUse, base_fields))

    if event == "Stop":
        base_fields["stop"] = StopFields(stopHookActive=False)
        return HookInputStop(**_filter_fields(HookInputStop, base_fields))

    return HookInput(**_filter_fields(HookInput, base_fields))
