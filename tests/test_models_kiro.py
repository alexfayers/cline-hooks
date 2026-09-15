from __future__ import annotations

from typing import Any

from cline_hooks.core.models import (
    HookInput,
    HookInputPostToolUse,
    HookInputPreToolUse,
    HookInputStop,
    HookInputTaskStart,
    HookInputUserPromptSubmit,
)
from cline_hooks.core.payload import map_tool_name
from cline_hooks.core.protocol import RawPayload
from cline_hooks.core.vocabulary import CanonicalTool
from cline_hooks.frontends.kiro import KiroProtocol


def _parse(data: dict[str, Any], env: dict[str, str] | None = None) -> HookInput:
    payload = RawPayload(raw="", data=data, env=env or {})
    return KiroProtocol().parse(payload)


class TestMapToolName:
    def test_shell(self) -> None:
        assert map_tool_name("shell", KiroProtocol) == "execute_command"

    def test_read(self) -> None:
        assert map_tool_name("read", KiroProtocol) == "read_file"

    def test_write(self) -> None:
        assert map_tool_name("write", KiroProtocol) == "replace_in_file"

    def test_mcp_tool(self) -> None:
        assert map_tool_name("@memory/create_entities", KiroProtocol) == "use_mcp_tool"

    def test_unknown_passthrough(self) -> None:
        assert map_tool_name("some_unknown_tool", KiroProtocol) == "some_unknown_tool"

    def test_use_aws(self) -> None:
        assert map_tool_name("use_aws", KiroProtocol) == "execute_command"

    def test_call_aws(self) -> None:
        assert map_tool_name("call_aws", KiroProtocol) == "execute_command"

    def test_web_fetch(self) -> None:
        assert map_tool_name("web_fetch", KiroProtocol) == CanonicalTool.WEB_FETCH

    def test_web_search(self) -> None:
        assert map_tool_name("web_search", KiroProtocol) == CanonicalTool.WEB_SEARCH


class TestNormaliseParameters:
    def test_read_extracts_path_from_operations(self) -> None:
        model = KiroProtocol.tool_models.get(CanonicalTool.READ)
        assert model is not None
        params = model.model_validate(
            {"operations": [{"mode": "Line", "path": "/file.py"}]}
        ).model_dump(exclude_none=True)
        assert params == {"path": "/file.py"}

    def test_read_empty_operations(self) -> None:
        model = KiroProtocol.tool_models.get(CanonicalTool.READ)
        assert model is not None
        params = model.model_validate({"operations": []}).model_dump(exclude_none=True)
        assert params == {}

    def test_read_no_operations(self) -> None:
        model = KiroProtocol.tool_models.get(CanonicalTool.READ)
        assert model is not None
        params = model.model_validate({}).model_dump(exclude_none=True)
        assert params == {}

    def test_write_str_replace(self) -> None:
        model = KiroProtocol.tool_models.get(CanonicalTool.EDIT)
        assert model is not None
        params = model.model_validate(
            {"command": "strReplace", "newStr": "# new code"}
        ).model_dump(exclude_none=True)
        assert "------- SEARCH" in params["diff"]
        assert "# new code" in params["diff"]
        assert "+++++++ REPLACE" in params["diff"]

    def test_write_create(self) -> None:
        model = KiroProtocol.tool_models.get(CanonicalTool.EDIT)
        assert model is not None
        params = model.model_validate(
            {"command": "create", "content": "# file content"}
        ).model_dump(exclude_none=True)
        assert "# file content" in params["diff"]

    def test_write_no_content(self) -> None:
        model = KiroProtocol.tool_models.get(CanonicalTool.EDIT)
        assert model is not None
        params = model.model_validate({"command": "strReplace"}).model_dump(
            exclude_none=True
        )
        assert params == {}

    def test_write_preserves_path(self) -> None:
        model = KiroProtocol.tool_models.get(CanonicalTool.EDIT)
        assert model is not None
        params = model.model_validate(
            {"command": "strReplace", "path": "/home/user/file.py", "newStr": "new"}
        ).model_dump(exclude_none=True)
        assert params["path"] == "/home/user/file.py"
        assert "new" in params["diff"]

    def test_write_no_content_preserves_path(self) -> None:
        model = KiroProtocol.tool_models.get(CanonicalTool.EDIT)
        assert model is not None
        params = model.model_validate(
            {"command": "strReplace", "path": "/home/user/file.py"}
        ).model_dump(exclude_none=True)
        assert params == {"path": "/home/user/file.py"}

    def test_passthrough_for_other_tools(self) -> None:
        original = {"command": "ls -la"}
        assert CanonicalTool.SHELL not in KiroProtocol.tool_models
        hook = _parse(
            {
                "hook_event_name": "preToolUse",
                "cwd": "/project",
                "tool_name": "shell",
                "tool_input": original,
            }
        )
        assert isinstance(hook, HookInputPreToolUse)
        assert hook.preToolUse is not None
        assert hook.preToolUse.parameters == original


class TestParseKiroPreToolUse:
    def test_basic(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "preToolUse",
                "cwd": "/home/user/project",
                "tool_name": "shell",
                "tool_input": {"command": "ls"},
            }
        )
        assert isinstance(hook, HookInputPreToolUse)
        assert hook.hookName == "PreToolUse"
        assert hook.preToolUse is not None
        assert hook.preToolUse.toolName == "execute_command"
        assert hook.preToolUse.parameters == {"command": "ls"}
        assert hook.workspaceRoots == ["/home/user/project"]

    def test_mcp_tool(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "preToolUse",
                "cwd": "/project",
                "tool_name": "@memory/create_entities",
                "tool_input": {"entities": []},
            }
        )
        assert isinstance(hook, HookInputPreToolUse)
        assert hook.preToolUse is not None
        assert hook.preToolUse.toolName == "use_mcp_tool"
        assert hook.preToolUse.parameters["server_name"] == "memory"
        assert hook.preToolUse.parameters["tool_name"] == "create_entities"

    def test_read_normalises_path(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "preToolUse",
                "cwd": "/project",
                "tool_name": "read",
                "tool_input": {
                    "operations": [{"mode": "Line", "path": "/project/big.py"}]
                },
            }
        )
        assert isinstance(hook, HookInputPreToolUse)
        assert hook.preToolUse is not None
        assert hook.preToolUse.parameters == {"path": "/project/big.py"}

    def test_write_normalises_diff(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "preToolUse",
                "cwd": "/project",
                "tool_name": "write",
                "tool_input": {"command": "strReplace", "newStr": "# a comment"},
            }
        )
        assert isinstance(hook, HookInputPreToolUse)
        assert hook.preToolUse is not None
        assert "# a comment" in hook.preToolUse.parameters["diff"]


class TestParseKiroPostToolUse:
    def test_basic(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "postToolUse",
                "cwd": "/project",
                "tool_name": "read",
                "tool_input": {"path": "/file.py"},
                "tool_response": {"success": True, "result": ["content"]},
            }
        )
        assert isinstance(hook, HookInputPostToolUse)
        assert hook.postToolUse is not None
        assert hook.postToolUse.toolName == "read_file"
        assert hook.postToolUse.success is True

    def test_failed(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "postToolUse",
                "cwd": "/project",
                "tool_name": "shell",
                "tool_input": {"command": "false"},
                "tool_response": {"success": False},
            }
        )
        assert isinstance(hook, HookInputPostToolUse)
        assert hook.postToolUse is not None
        assert hook.postToolUse.success is False

    def test_string_tool_response(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "postToolUse",
                "cwd": "/project",
                "tool_name": "read",
                "tool_input": {"path": "/file.py"},
                "tool_response": "some string result",
            }
        )
        assert isinstance(hook, HookInputPostToolUse)
        assert hook.postToolUse is not None
        assert hook.postToolUse.success is True

    def test_list_tool_response(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "postToolUse",
                "cwd": "/project",
                "tool_name": "shell",
                "tool_input": {"command": "ls"},
                "tool_response": ["line1", "line2"],
            }
        )
        assert isinstance(hook, HookInputPostToolUse)
        assert hook.postToolUse is not None
        assert hook.postToolUse.success is True

    def test_string_tool_input(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "preToolUse",
                "cwd": "/project",
                "tool_name": "shell",
                "tool_input": "not a dict",
            }
        )
        assert isinstance(hook, HookInputPreToolUse)
        assert hook.preToolUse is not None
        assert hook.preToolUse.parameters == {}

    def test_web_fetch_maps_to_canonical_name(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "postToolUse",
                "cwd": "/project",
                "tool_name": "web_fetch",
                "tool_input": {"url": "https://example.com/docs", "mode": "full"},
                "tool_response": {"success": True},
            }
        )
        assert isinstance(hook, HookInputPostToolUse)
        assert hook.postToolUse is not None
        assert hook.postToolUse.toolName == CanonicalTool.WEB_FETCH
        assert hook.postToolUse.parameters["url"] == "https://example.com/docs"

    def test_web_search_maps_to_canonical_name(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "postToolUse",
                "cwd": "/project",
                "tool_name": "web_search",
                "tool_input": {"query": "kiro cli hooks"},
                "tool_response": {"success": True},
            }
        )
        assert isinstance(hook, HookInputPostToolUse)
        assert hook.postToolUse is not None
        assert hook.postToolUse.toolName == CanonicalTool.WEB_SEARCH
        assert hook.postToolUse.parameters["query"] == "kiro cli hooks"


class TestParseKiroAgentSpawn:
    def test_maps_to_task_start(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "agentSpawn",
                "cwd": "/home/user/project",
            }
        )
        assert isinstance(hook, HookInputTaskStart)
        assert hook.hookName == "TaskStart"
        assert hook.workspaceRoots == ["/home/user/project"]
        assert hook.taskId != ""
        assert len(hook.taskId) == 16

    def test_session_id_used_as_task_id(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "agentSpawn",
                "cwd": "/home/user/project",
                "session_id": "abc-123-uuid",
            }
        )
        assert isinstance(hook, HookInputTaskStart)
        assert hook.taskId == "abc-123-uuid"

    def test_falls_back_to_cwd_hash_without_session_id(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "agentSpawn",
                "cwd": "/home/user/project",
            }
        )
        assert isinstance(hook, HookInputTaskStart)
        assert len(hook.taskId) == 16

    def test_kiro_session_id_env_var_used(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "agentSpawn",
                "cwd": "/home/user/project",
            },
            env={"KIRO_SESSION_ID": "env-uuid-value"},
        )
        assert isinstance(hook, HookInputTaskStart)
        assert hook.taskId == "env-uuid-value"

    def test_source_captured(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "agentSpawn",
                "cwd": "/project",
                "session_id": "s1",
                "source": "compact",
            }
        )
        assert isinstance(hook, HookInputTaskStart)
        assert hook.taskStart is not None
        assert hook.taskStart.source == "compact"


class TestParseKiroUserPromptSubmit:
    def test_basic(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "userPromptSubmit",
                "cwd": "/project",
                "prompt": "hello world",
            }
        )
        assert isinstance(hook, HookInputUserPromptSubmit)
        assert hook.userPromptSubmit is not None
        assert hook.userPromptSubmit.userMessage == "hello world"

    def test_captures_transcript_path(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "userPromptSubmit",
                "cwd": "/project",
                "prompt": "hello",
                "transcript_path": "session.jsonl",
            }
        )
        assert hook.transcriptPath == "session.jsonl"

    def test_captures_agent_type(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "preToolUse",
                "cwd": "/project",
                "tool_name": "read",
                "tool_input": {"operations": [{"path": "/file.py"}]},
                "agent_type": "Explore",
            }
        )
        assert hook.agentType == "Explore"

    def test_agent_type_defaults_empty(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "preToolUse",
                "cwd": "/project",
                "tool_name": "read",
                "tool_input": {"operations": [{"path": "/file.py"}]},
            }
        )
        assert hook.agentType == ""


class TestParseKiroStop:
    def test_basic(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "stop",
                "cwd": "/project",
            }
        )
        assert isinstance(hook, HookInputStop)
        assert hook.hookName == "Stop"
        assert hook.stop is not None
        assert hook.stop.stopHookActive is False

    def test_stop_hook_active_true(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "stop",
                "cwd": "/project",
                "stop_hook_active": True,
            }
        )
        assert isinstance(hook, HookInputStop)
        assert hook.stop is not None
        assert hook.stop.stopHookActive is True


class TestKiroDetect:
    def test_detects_native_hook_names(self) -> None:
        for native_name in (
            "preToolUse",
            "postToolUse",
            "agentSpawn",
            "userPromptSubmit",
            "stop",
        ):
            payload = RawPayload(raw="", data={"hook_event_name": native_name}, env={})
            assert KiroProtocol.detect(payload) is True

    def test_rejects_unknown_hook_name(self) -> None:
        payload = RawPayload(raw="", data={"hook_event_name": "SessionStart"}, env={})
        assert KiroProtocol.detect(payload) is False

    def test_rejects_missing_data(self) -> None:
        payload = RawPayload(raw="not json", data=None, env={})
        assert KiroProtocol.detect(payload) is False


class TestParseKiroUnknownHook:
    def test_returns_base(self) -> None:
        hook = _parse(
            {
                "hook_event_name": "someUnknownHook",
                "cwd": "/project",
            }
        )
        assert isinstance(hook, HookInput)
        assert hook.hookName == "someUnknownHook"
