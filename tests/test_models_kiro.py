from __future__ import annotations

import json

from cline_hooks.core.models import (
    HookInput,
    HookInputPostToolUse,
    HookInputPreToolUse,
    HookInputTaskStart,
    HookInputUserPromptSubmit,
)
from cline_hooks.frontends.kiro import parse_kiro_data
from cline_hooks.frontends.kiro.parser import _map_tool_name, _normalise_parameters


class TestMapToolName:
    def test_shell(self) -> None:
        assert _map_tool_name("shell") == "execute_command"

    def test_read(self) -> None:
        assert _map_tool_name("read") == "read_file"

    def test_write(self) -> None:
        assert _map_tool_name("write") == "replace_in_file"

    def test_mcp_tool(self) -> None:
        assert _map_tool_name("@memory/create_entities") == "use_mcp_tool"

    def test_unknown_passthrough(self) -> None:
        assert _map_tool_name("grep") == "grep"

    def test_use_aws(self) -> None:
        assert _map_tool_name("use_aws") == "execute_command"

    def test_call_aws(self) -> None:
        assert _map_tool_name("call_aws") == "execute_command"


class TestNormaliseParameters:
    def test_read_extracts_path_from_operations(self) -> None:
        params = _normalise_parameters("read", {"operations": [{"mode": "Line", "path": "/file.py"}]})
        assert params == {"path": "/file.py"}

    def test_read_empty_operations(self) -> None:
        assert _normalise_parameters("read", {"operations": []}) == {}

    def test_read_no_operations(self) -> None:
        assert _normalise_parameters("read", {}) == {}

    def test_write_str_replace(self) -> None:
        params = _normalise_parameters("write", {"command": "strReplace", "newStr": "# new code"})
        assert "------- SEARCH" in params["diff"]
        assert "# new code" in params["diff"]
        assert "+++++++ REPLACE" in params["diff"]

    def test_write_create(self) -> None:
        params = _normalise_parameters("write", {"command": "create", "content": "# file content"})
        assert "# file content" in params["diff"]

    def test_write_no_content(self) -> None:
        assert _normalise_parameters("write", {"command": "strReplace"}) == {}

    def test_passthrough_for_other_tools(self) -> None:
        original = {"command": "ls -la"}
        assert _normalise_parameters("shell", original) is original


class TestParseKiroPreToolUse:
    def test_basic(self) -> None:
        data = json.dumps({
            "hook_event_name": "preToolUse",
            "cwd": "/home/user/project",
            "tool_name": "shell",
            "tool_input": {"command": "ls"},
        })
        hook = parse_kiro_data(data)
        assert isinstance(hook, HookInputPreToolUse)
        assert hook.hookName == "PreToolUse"
        assert hook.preToolUse is not None
        assert hook.preToolUse.toolName == "execute_command"
        assert hook.preToolUse.parameters == {"command": "ls"}
        assert hook.workspaceRoots == ["/home/user/project"]

    def test_mcp_tool(self) -> None:
        data = json.dumps({
            "hook_event_name": "preToolUse",
            "cwd": "/project",
            "tool_name": "@memory/create_entities",
            "tool_input": {"entities": []},
        })
        hook = parse_kiro_data(data)
        assert isinstance(hook, HookInputPreToolUse)
        assert hook.preToolUse is not None
        assert hook.preToolUse.toolName == "use_mcp_tool"
        assert hook.preToolUse.parameters["server_name"] == "memory"
        assert hook.preToolUse.parameters["tool_name"] == "create_entities"

    def test_read_normalises_path(self) -> None:
        data = json.dumps({
            "hook_event_name": "preToolUse",
            "cwd": "/project",
            "tool_name": "read",
            "tool_input": {"operations": [{"mode": "Line", "path": "/project/big.py"}]},
        })
        hook = parse_kiro_data(data)
        assert isinstance(hook, HookInputPreToolUse)
        assert hook.preToolUse is not None
        assert hook.preToolUse.parameters == {"path": "/project/big.py"}

    def test_write_normalises_diff(self) -> None:
        data = json.dumps({
            "hook_event_name": "preToolUse",
            "cwd": "/project",
            "tool_name": "write",
            "tool_input": {"command": "strReplace", "newStr": "# a comment"},
        })
        hook = parse_kiro_data(data)
        assert isinstance(hook, HookInputPreToolUse)
        assert hook.preToolUse is not None
        assert "# a comment" in hook.preToolUse.parameters["diff"]


class TestParseKiroPostToolUse:
    def test_basic(self) -> None:
        data = json.dumps({
            "hook_event_name": "postToolUse",
            "cwd": "/project",
            "tool_name": "read",
            "tool_input": {"path": "/file.py"},
            "tool_response": {"success": True, "result": ["content"]},
        })
        hook = parse_kiro_data(data)
        assert isinstance(hook, HookInputPostToolUse)
        assert hook.postToolUse is not None
        assert hook.postToolUse.toolName == "read_file"
        assert hook.postToolUse.success is True

    def test_failed(self) -> None:
        data = json.dumps({
            "hook_event_name": "postToolUse",
            "cwd": "/project",
            "tool_name": "shell",
            "tool_input": {"command": "false"},
            "tool_response": {"success": False},
        })
        hook = parse_kiro_data(data)
        assert isinstance(hook, HookInputPostToolUse)
        assert hook.postToolUse is not None
        assert hook.postToolUse.success is False


class TestParseKiroAgentSpawn:
    def test_maps_to_task_start(self) -> None:
        data = json.dumps({
            "hook_event_name": "agentSpawn",
            "cwd": "/home/user/project",
        })
        hook = parse_kiro_data(data)
        assert isinstance(hook, HookInputTaskStart)
        assert hook.hookName == "TaskStart"
        assert hook.workspaceRoots == ["/home/user/project"]
        assert hook.taskId != ""
        assert len(hook.taskId) == 16


class TestParseKiroUserPromptSubmit:
    def test_basic(self) -> None:
        data = json.dumps({
            "hook_event_name": "userPromptSubmit",
            "cwd": "/project",
            "prompt": "hello world",
        })
        hook = parse_kiro_data(data)
        assert isinstance(hook, HookInputUserPromptSubmit)
        assert hook.userPromptSubmit is not None
        assert hook.userPromptSubmit.userMessage == "hello world"


class TestParseKiroUnknownHook:
    def test_returns_base(self) -> None:
        data = json.dumps({
            "hook_event_name": "stop",
            "cwd": "/project",
        })
        hook = parse_kiro_data(data)
        assert isinstance(hook, HookInput)
        assert hook.hookName == "Stop"
