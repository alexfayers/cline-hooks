from __future__ import annotations

import json

import pytest

from cline_hooks._main import _detect_antigravity
from cline_hooks.core.models import (
    HookInputPostToolUse,
    HookInputPreToolUse,
    HookInputStop,
)
from cline_hooks.frontends.antigravity import AntigravityProtocol, parse_antigravity_data


class TestAntigravityProtocol:
    def test_pre_tool_use_allow(self, capsys: pytest.CaptureFixture[str]) -> None:
        protocol = AntigravityProtocol("PreToolUse")
        with pytest.raises(SystemExit) as exc_info:
            protocol.allow()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"decision": "allow"}

    def test_pre_tool_use_block(self, capsys: pytest.CaptureFixture[str]) -> None:
        protocol = AntigravityProtocol("PreToolUse")
        with pytest.raises(SystemExit) as exc_info:
            protocol.block("Dangerous command blocked")
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {
            "decision": "deny",
            "reason": "Dangerous command blocked",
        }

    def test_stop_allow(self, capsys: pytest.CaptureFixture[str]) -> None:
        protocol = AntigravityProtocol("Stop")
        with pytest.raises(SystemExit) as exc_info:
            protocol.allow()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"decision": "allow"}

    def test_stop_feedback(self, capsys: pytest.CaptureFixture[str]) -> None:
        protocol = AntigravityProtocol("Stop")
        with pytest.raises(SystemExit) as exc_info:
            protocol.feedback("Uncommitted changes exist")
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {
            "decision": "continue",
            "reason": "Uncommitted changes exist",
        }

    def test_post_tool_use_allow(self, capsys: pytest.CaptureFixture[str]) -> None:
        protocol = AntigravityProtocol("PostToolUse")
        with pytest.raises(SystemExit) as exc_info:
            protocol.allow()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {}


class TestParseAntigravityData:
    def test_detect_antigravity(self) -> None:
        valid_payload = json.dumps({
            "conversationId": "test-123",
            "toolCall": {"name": "run_command", "args": {"CommandLine": "ls"}},
        })
        assert _detect_antigravity(valid_payload) is True

        kiro_payload = json.dumps({"hook_event_name": "preToolUse"})
        assert _detect_antigravity(kiro_payload) is False

    def test_parse_pre_tool_use_run_command(self) -> None:
        payload = json.dumps({
            "conversationId": "conv-456",
            "workspacePaths": ["/path/to/project"],
            "toolCall": {
                "name": "run_command",
                "args": {
                    "CommandLine": "echo 'hello'",
                    "Cwd": "/path/to/project",
                },
            },
        })
        hook = parse_antigravity_data(payload)
        assert isinstance(hook, HookInputPreToolUse)
        assert hook.taskId == "conv-456"
        assert hook.workspaceRoots == ["/path/to/project"]
        assert hook.preToolUse is not None
        assert hook.preToolUse.toolName == "execute_command"
        assert hook.preToolUse.parameters["command"] == "echo 'hello'"

    def test_parse_pre_tool_use_write_to_file(self) -> None:
        payload = json.dumps({
            "conversationId": "conv-456",
            "workspacePaths": ["/path/to/project"],
            "toolCall": {
                "name": "write_to_file",
                "args": {
                    "TargetFile": "/path/to/project/foo.py",
                    "CodeContent": "print('hello')",
                },
            },
        })
        hook = parse_antigravity_data(payload)
        assert isinstance(hook, HookInputPreToolUse)
        assert hook.preToolUse is not None
        assert hook.preToolUse.toolName == "write_to_file"
        assert hook.preToolUse.parameters["path"] == "/path/to/project/foo.py"
        assert hook.preToolUse.parameters["content"] == "print('hello')"

    def test_parse_pre_tool_use_replace_file_content(self) -> None:
        payload = json.dumps({
            "conversationId": "conv-456",
            "toolCall": {
                "name": "replace_file_content",
                "args": {
                    "TargetFile": "/path/to/project/foo.py",
                    "ReplacementContent": "print('world')",
                },
            },
        })
        hook = parse_antigravity_data(payload)
        assert isinstance(hook, HookInputPreToolUse)
        assert hook.preToolUse is not None
        assert hook.preToolUse.toolName == "replace_in_file"
        assert hook.preToolUse.parameters["path"] == "/path/to/project/foo.py"

    def test_parse_pre_tool_use_view_file(self) -> None:
        payload = json.dumps({
            "conversationId": "conv-456",
            "toolCall": {
                "name": "view_file",
                "args": {"AbsolutePath": "/path/to/project/README.md"},
            },
        })
        hook = parse_antigravity_data(payload)
        assert isinstance(hook, HookInputPreToolUse)
        assert hook.preToolUse is not None
        assert hook.preToolUse.toolName == "read_file"
        assert hook.preToolUse.parameters["path"] == "/path/to/project/README.md"

    def test_parse_stop(self) -> None:
        payload = json.dumps({
            "conversationId": "conv-789",
            "executionNum": 1,
            "terminationReason": "model_stop",
        })
        hook = parse_antigravity_data(payload)
        assert isinstance(hook, HookInputStop)
        assert hook.taskId == "conv-789"
        assert hook.stop is not None

    def test_parse_post_tool_use(self) -> None:
        payload = json.dumps({
            "conversationId": "conv-789",
            "stepIdx": 3,
            "error": "Command failed with exit code 1",
        })
        hook = parse_antigravity_data(payload)
        assert isinstance(hook, HookInputPostToolUse)
        assert hook.taskId == "conv-789"
        assert hook.postToolUse is not None
        assert hook.postToolUse.success is False
