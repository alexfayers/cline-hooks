from __future__ import annotations

import json
import subprocess
import sys

from cline_hooks._main import _detect_kiro, _parse_input
from cline_hooks.frontends.cline import ClineProtocol
from cline_hooks.frontends.kiro import KiroProtocol
from cline_hooks.models import HookInputPreToolUse, HookInputTaskStart
import cline_hooks.protocol as protocol_module


class TestDetectKiro:
    def test_kiro_input(self) -> None:
        data = json.dumps({"hook_event_name": "preToolUse", "cwd": "/project"})
        assert _detect_kiro(data) is True

    def test_cline_input(self) -> None:
        data = json.dumps({"hookName": "PreToolUse", "taskId": "abc"})
        assert _detect_kiro(data) is False


class TestParseInput:
    def test_kiro_sets_kiro_protocol(self) -> None:
        data = json.dumps({
            "hook_event_name": "agentSpawn",
            "cwd": "/project",
        })
        hook = _parse_input(data)
        assert isinstance(hook, HookInputTaskStart)
        assert isinstance(protocol_module._active_protocol, KiroProtocol)

    def test_cline_sets_cline_protocol(self) -> None:
        data = json.dumps({
            "hookName": "PreToolUse",
            "taskId": "t1",
            "workspaceRoots": [],
            "preToolUse": {"toolName": "read_file", "parameters": {}},
        })
        hook = _parse_input(data)
        assert isinstance(hook, HookInputPreToolUse)
        assert isinstance(protocol_module._active_protocol, ClineProtocol)


class TestEndToEndKiro:
    def test_pre_tool_use_block_rm_rf(self) -> None:
        """Kiro preToolUse with rm -rf should exit 2 with error on stderr."""
        data = json.dumps({
            "hook_event_name": "preToolUse",
            "cwd": "/tmp/test",  # noqa: S108
            "tool_name": "execute_bash",
            "tool_input": {"command": "rm -rf /tmp/test"},
        })
        result = subprocess.run(
            [sys.executable, "-m", "cline_hooks"],
            input=data,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 2
        assert "rm -f is not allowed" in result.stderr

    def test_pre_tool_use_allow_safe_command(self) -> None:
        """Kiro preToolUse with safe command should exit 0."""
        data = json.dumps({
            "hook_event_name": "preToolUse",
            "cwd": "/tmp/test",  # noqa: S108
            "tool_name": "execute_bash",
            "tool_input": {"command": "ls -la"},
        })
        result = subprocess.run(
            [sys.executable, "-m", "cline_hooks"],
            input=data,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
