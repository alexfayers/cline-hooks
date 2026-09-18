from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

from cline_hooks.core.frontends import select_protocol
from cline_hooks.core.models import HookInputPreToolUse, HookInputTaskStart
import cline_hooks.core.protocol as protocol_module
from cline_hooks.core.protocol import RawPayload, set_protocol
from cline_hooks.frontends.claude_code import ClaudeCodeProtocol
from cline_hooks.frontends.cline import ClineProtocol
from cline_hooks.frontends.kiro import KiroProtocol

if TYPE_CHECKING:
    from collections.abc import Mapping

    from cline_hooks.core.models import HookInput

_KIRO_ENV = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}


def _dispatch(raw: str, env: Mapping[str, str] | None = None) -> HookInput:
    """Run the real _main.py dispatch sequence against explicit, controlled env.

    Mirrors `_run_hook`'s production sequence exactly, but with an explicit
    `env` (rather than `RawPayload.from_stdin`'s real `os.environ`) so these
    tests aren't at the mercy of whatever env vars the test runner's own
    process happens to carry (e.g. `CLAUDECODE=1` when run under Claude Code
    itself).

    Returns:
        The parsed HookInput, with the active protocol left set as a side effect.
    """
    payload = RawPayload(raw=raw, data=json.loads(raw), env=env or {})
    proto = select_protocol(payload).from_payload(payload)
    set_protocol(proto)
    proto.configure_logging()
    return proto.parse(payload)


class TestDispatch:
    def test_kiro_sets_kiro_protocol(self) -> None:
        data = json.dumps({
            "hook_event_name": "agentSpawn",
            "cwd": "/project",
        })
        hook = _dispatch(data)
        assert isinstance(hook, HookInputTaskStart)
        assert isinstance(protocol_module._active_protocol, KiroProtocol)

    def test_cline_sets_cline_protocol(self) -> None:
        data = json.dumps({
            "hookName": "PreToolUse",
            "taskId": "t1",
            "workspaceRoots": [],
            "preToolUse": {"toolName": "read_file", "parameters": {}},
        })
        hook = _dispatch(data)
        assert isinstance(hook, HookInputPreToolUse)
        assert isinstance(protocol_module._active_protocol, ClineProtocol)

    def test_claude_code_stop_sets_claude_code_protocol(self) -> None:
        data = json.dumps({"hook_event_name": "Stop", "cwd": "/project"})
        _dispatch(data)
        assert isinstance(protocol_module._active_protocol, ClaudeCodeProtocol)

    def test_kiro_stop_sets_kiro_protocol(self) -> None:
        data = json.dumps({"hook_event_name": "stop", "cwd": "/project"})
        _dispatch(data)
        assert isinstance(protocol_module._active_protocol, KiroProtocol)
        assert not isinstance(protocol_module._active_protocol, ClaudeCodeProtocol)

    def test_claude_code_session_start_maps_to_taskstart(self) -> None:
        data = json.dumps({"hook_event_name": "SessionStart", "cwd": "/project"})
        hook = _dispatch(data)
        assert isinstance(hook, HookInputTaskStart)
        assert isinstance(protocol_module._active_protocol, ClaudeCodeProtocol)


class TestEndToEndKiro:
    def test_pre_tool_use_block_rm_rf(self) -> None:
        """Kiro preToolUse with rm -rf should exit 2 with error on stderr."""
        data = json.dumps({
            "hook_event_name": "preToolUse",
            "cwd": "/tmp/test",
            "tool_name": "shell",
            "tool_input": {"command": "rm -rf /tmp/test"},
        })
        result = subprocess.run(
            [sys.executable, "-m", "cline_hooks"],
            input=data,
            capture_output=True,
            text=True,
            check=False,
            env=_KIRO_ENV,
        )
        assert result.returncode == 2
        assert "rm -f is not allowed" in result.stderr

    def test_pre_tool_use_allow_safe_command(self) -> None:
        """Kiro preToolUse with safe command should exit 0."""
        data = json.dumps({
            "hook_event_name": "preToolUse",
            "cwd": "/tmp/test",
            "tool_name": "shell",
            "tool_input": {"command": "ls -la"},
        })
        result = subprocess.run(
            [sys.executable, "-m", "cline_hooks"],
            input=data,
            capture_output=True,
            text=True,
            check=False,
            env=_KIRO_ENV,
        )
        assert result.returncode == 0
