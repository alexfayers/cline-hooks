from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from cline_hooks.core.models import (
    HookInput,
    HookInputPostToolUse,
    HookInputPreToolUse,
)
from cline_hooks.core.protocol import Protocol, RawPayload
from cline_hooks.frontends.claude_code.protocol import ClaudeCodeProtocol
from cline_hooks.frontends.cline.protocol import ClineProtocol
from cline_hooks.frontends.codex.protocol import CodexProtocol
from cline_hooks.frontends.copilot.protocol import CopilotProtocol
from cline_hooks.frontends.kiro.protocol import KiroProtocol

FIXTURES_DIR = Path(__file__).parent / "fixtures"

_CLAUDE_CODE_ENVELOPE: dict[str, Any] = {
    "taskId": "fixture-session-id",
    "workspaceRoots": ["/home/user/project"],
    "transcriptPath": "/home/user/.claude/projects/fixture/transcript.jsonl",
    "agentType": "",
}
_KIRO_ENVELOPE: dict[str, Any] = {
    "taskId": "fixture-session-id",
    "workspaceRoots": ["/home/user/project"],
    "transcriptPath": "",
    "agentType": "",
}
_COPILOT_ENVELOPE: dict[str, Any] = {
    "taskId": "fixture-session-id",
    "workspaceRoots": ["/home/user/project"],
    "transcriptPath": "",
    "agentType": "",
}
_CLINE_ENVELOPE: dict[str, Any] = {
    "taskId": "fixture-task-1",
    "workspaceRoots": ["/home/user/project"],
    "transcriptPath": "",
    "agentType": "",
}


def _fixture_path(frontend: str, name: str) -> Path:
    """Resolve a fixture path under the hook-type-first fixture layout.

    Args:
        frontend: The frontend's fixture file stem.
        name: A canonical hook name, or "tools/<ToolName>" for a per-tool PreToolUse fixture.

    Returns:
        The fixture file path.
    """
    if name.startswith("tools/"):
        tool = name.removeprefix("tools/")
        return FIXTURES_DIR / "PreToolUse" / "tools" / f"{frontend}_{tool}.json"
    return FIXTURES_DIR / name / f"{frontend}.json"


def _parse(
    frontend: str,
    name: str,
    protocol_cls: type[Protocol],
    env: Mapping[str, str] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> HookInput:
    """Parse a fixture file through one frontend's protocol.

    Args:
        frontend: The frontend's fixture file stem.
        name: The fixture stem, optionally prefixed with "tools/".
        protocol_cls: The protocol whose parse() to exercise.
        env: Process environment the protocol may read for session id.
        overrides: Top-level payload keys to replace before parsing.

    Returns:
        The normalised HookInput.
    """
    data = json.loads(_fixture_path(frontend, name).read_text())
    if overrides:
        data = {**data, **overrides}
    raw = json.dumps(data)
    return protocol_cls().parse(RawPayload(raw=raw, data=data, env=env or {}))


class TestClaudeCodeNormalisation:
    def test_pre_tool_use(self) -> None:
        hook = _parse("claude-code", "PreToolUse", ClaudeCodeProtocol)
        assert hook.model_dump() == {
            **_CLAUDE_CODE_ENVELOPE,
            "hookName": "PreToolUse",
            "preToolUse": {
                "toolName": "execute_command",
                "parameters": {"command": "ls -la"},
            },
        }

    def test_post_tool_use(self) -> None:
        hook = _parse("claude-code", "PostToolUse", ClaudeCodeProtocol)
        assert hook.model_dump() == {
            **_CLAUDE_CODE_ENVELOPE,
            "hookName": "PostToolUse",
            "postToolUse": {
                "toolName": "execute_command",
                "parameters": {"command": "ls -la"},
                "success": True,
                "executionTimeMs": 0,
                "result": None,
            },
        }

    def test_task_start(self) -> None:
        hook = _parse("claude-code", "TaskStart", ClaudeCodeProtocol)
        assert hook.model_dump() == {
            **_CLAUDE_CODE_ENVELOPE,
            "hookName": "TaskStart",
            "taskStart": {"task": "", "source": "startup"},
        }

    def test_user_prompt_submit(self) -> None:
        hook = _parse("claude-code", "UserPromptSubmit", ClaudeCodeProtocol)
        assert hook.model_dump() == {
            **_CLAUDE_CODE_ENVELOPE,
            "hookName": "UserPromptSubmit",
            "userPromptSubmit": {"userMessage": "Add a new test for the parser."},
        }

    def test_stop(self) -> None:
        hook = _parse("claude-code", "Stop", ClaudeCodeProtocol)
        assert hook.model_dump() == {
            **_CLAUDE_CODE_ENVELOPE,
            "hookName": "Stop",
            "stop": {"stopHookActive": False},
        }

    def test_tools_read(self) -> None:
        hook = _parse("claude-code", "tools/Read", ClaudeCodeProtocol)
        assert hook.model_dump() == {
            **_CLAUDE_CODE_ENVELOPE,
            "hookName": "PreToolUse",
            "preToolUse": {
                "toolName": "read_file",
                "parameters": {"path": "/home/user/project/README.md"},
            },
        }

    def test_tools_edit(self) -> None:
        hook = _parse("claude-code", "tools/Edit", ClaudeCodeProtocol)
        assert hook.model_dump() == {
            **_CLAUDE_CODE_ENVELOPE,
            "hookName": "PreToolUse",
            "preToolUse": {
                "toolName": "replace_in_file",
                "parameters": {
                    "path": "/home/user/project/src/app.py",
                    "diff": "------- SEARCH\n=======\nnew line\n+++++++ REPLACE",
                },
            },
        }

    def test_tools_write(self) -> None:
        hook = _parse("claude-code", "tools/Write", ClaudeCodeProtocol)
        assert hook.model_dump() == {
            **_CLAUDE_CODE_ENVELOPE,
            "hookName": "PreToolUse",
            "preToolUse": {
                "toolName": "write_to_file",
                "parameters": {
                    "path": "/home/user/project/notes.md",
                    "diff": "------- SEARCH\n=======\nhello\nworld\n+++++++ REPLACE",
                },
            },
        }

    def test_tools_mcp(self) -> None:
        hook = _parse("claude-code", "tools/Mcp", ClaudeCodeProtocol)
        assert hook.model_dump() == {
            **_CLAUDE_CODE_ENVELOPE,
            "hookName": "PreToolUse",
            "preToolUse": {
                "toolName": "use_mcp_tool",
                "parameters": {
                    "server_name": "memory",
                    "tool_name": "create_entities",
                    "arguments": json.dumps(
                        {"project": "demo", "entities": [{"name": "e1"}]}
                    ),
                },
            },
        }


class TestKiroNormalisation:
    def test_pre_tool_use(self) -> None:
        hook = _parse("kiro", "PreToolUse", KiroProtocol)
        assert hook.model_dump() == {
            **_KIRO_ENVELOPE,
            "hookName": "PreToolUse",
            "preToolUse": {
                "toolName": "execute_command",
                "parameters": {"command": "ls -la"},
            },
        }

    def test_post_tool_use(self) -> None:
        hook = _parse("kiro", "PostToolUse", KiroProtocol)
        assert hook.model_dump() == {
            **_KIRO_ENVELOPE,
            "hookName": "PostToolUse",
            "postToolUse": {
                "toolName": "execute_command",
                "parameters": {"command": "ls -la"},
                "success": True,
                "executionTimeMs": 0,
                "result": "file1\nfile2",
            },
        }

    def test_task_start(self) -> None:
        hook = _parse("kiro", "TaskStart", KiroProtocol)
        assert hook.model_dump() == {
            **_KIRO_ENVELOPE,
            "hookName": "TaskStart",
            "taskStart": {"task": "", "source": "startup"},
        }

    def test_user_prompt_submit(self) -> None:
        hook = _parse("kiro", "UserPromptSubmit", KiroProtocol)
        assert hook.model_dump() == {
            **_KIRO_ENVELOPE,
            "hookName": "UserPromptSubmit",
            "userPromptSubmit": {"userMessage": "Add a new test for the parser."},
        }

    def test_stop(self) -> None:
        hook = _parse("kiro", "Stop", KiroProtocol)
        assert hook.model_dump() == {
            **_KIRO_ENVELOPE,
            "hookName": "Stop",
            "stop": {"stopHookActive": False},
        }

    def test_tools_shell(self) -> None:
        hook = _parse("kiro", "tools/Shell", KiroProtocol)
        assert hook.model_dump() == {
            **_KIRO_ENVELOPE,
            "hookName": "PreToolUse",
            "preToolUse": {
                "toolName": "execute_command",
                "parameters": {"command": "ls -la", "summary": "list files"},
            },
        }

    def test_tools_read(self) -> None:
        hook = _parse("kiro", "tools/Read", KiroProtocol)
        assert hook.model_dump() == {
            **_KIRO_ENVELOPE,
            "hookName": "PreToolUse",
            "preToolUse": {
                "toolName": "read_file",
                "parameters": {"path": "/home/user/project/README.md"},
            },
        }

    def test_tools_grep(self) -> None:
        hook = _parse("kiro", "tools/Grep", KiroProtocol)
        assert hook.model_dump() == {
            **_KIRO_ENVELOPE,
            "hookName": "PreToolUse",
            "preToolUse": {"toolName": "read_file", "parameters": {}},
        }

    def test_tools_write(self) -> None:
        hook = _parse("kiro", "tools/Write", KiroProtocol)
        assert hook.model_dump() == {
            **_KIRO_ENVELOPE,
            "hookName": "PreToolUse",
            "preToolUse": {
                "toolName": "replace_in_file",
                "parameters": {
                    "path": "/home/user/project/src/app.py",
                    "diff": "------- SEARCH\n=======\nnew line\n+++++++ REPLACE",
                },
            },
        }

    def test_stop_session_id_falls_back_to_kiro_env_var(self) -> None:
        hook = _parse(
            "kiro",
            "Stop",
            KiroProtocol,
            env={"KIRO_SESSION_ID": "kiro-env-session"},
            overrides={"session_id": ""},
        )
        assert hook.model_dump() == {
            **_KIRO_ENVELOPE,
            "taskId": "kiro-env-session",
            "hookName": "Stop",
            "stop": {"stopHookActive": False},
        }


class TestClineNormalisation:
    def test_pre_tool_use(self) -> None:
        hook = _parse("cline", "PreToolUse", ClineProtocol)
        assert hook.model_dump() == {
            **_CLINE_ENVELOPE,
            "hookName": "PreToolUse",
            "preToolUse": {
                "toolName": "execute_command",
                "parameters": {"command": "ls -la"},
            },
        }

    def test_post_tool_use(self) -> None:
        hook = _parse("cline", "PostToolUse", ClineProtocol)
        assert hook.model_dump() == {
            **_CLINE_ENVELOPE,
            "hookName": "PostToolUse",
            "postToolUse": {
                "toolName": "execute_command",
                "parameters": {"command": "ls -la"},
                "success": True,
                "executionTimeMs": 42,
                "result": "file1\nfile2",
            },
        }

    def test_task_start(self) -> None:
        hook = _parse("cline", "TaskStart", ClineProtocol)
        assert hook.model_dump() == {
            **_CLINE_ENVELOPE,
            "hookName": "TaskStart",
            "taskStart": {
                "task": "Add a new test for the parser.",
                "source": "startup",
            },
        }

    def test_task_resume(self) -> None:
        hook = _parse("cline", "TaskResume", ClineProtocol)
        assert hook.model_dump() == {
            **_CLINE_ENVELOPE,
            "hookName": "TaskResume",
            "taskResume": {"task": "Add a new test for the parser."},
        }

    def test_task_cancel(self) -> None:
        hook = _parse("cline", "TaskCancel", ClineProtocol)
        assert hook.model_dump() == {
            **_CLINE_ENVELOPE,
            "hookName": "TaskCancel",
            "taskCancel": {},
        }

    def test_task_complete(self) -> None:
        hook = _parse("cline", "TaskComplete", ClineProtocol)
        assert hook.model_dump() == {
            **_CLINE_ENVELOPE,
            "hookName": "TaskComplete",
            "taskComplete": {},
        }

    def test_user_prompt_submit(self) -> None:
        hook = _parse("cline", "UserPromptSubmit", ClineProtocol)
        assert hook.model_dump() == {
            **_CLINE_ENVELOPE,
            "hookName": "UserPromptSubmit",
            "userPromptSubmit": {"userMessage": "Add a new test for the parser."},
        }

    def test_pre_compact(self) -> None:
        hook = _parse("cline", "PreCompact", ClineProtocol)
        assert hook.model_dump() == {
            **_CLINE_ENVELOPE,
            "hookName": "PreCompact",
            "preCompact": {"conversationLength": 42, "estimatedTokens": 128000},
        }

    def test_stop(self) -> None:
        hook = _parse("cline", "Stop", ClineProtocol)
        assert hook.model_dump() == {
            **_CLINE_ENVELOPE,
            "transcriptPath": "/home/user/.cline/tasks/fixture-task-1/ui_messages.json",
            "hookName": "Stop",
            "stop": {"stopHookActive": False},
        }

    def test_tools_new_task(self) -> None:
        hook = _parse("cline", "tools/NewTask", ClineProtocol)
        assert hook.model_dump() == {
            **_CLINE_ENVELOPE,
            "hookName": "PreToolUse",
            "preToolUse": {
                "toolName": "spawn_agent",
                "parameters": {"context": "spawn a subagent"},
            },
        }


class TestCopilotNormalisation:
    def test_pre_tool_use(self) -> None:
        hook = _parse("copilot", "PreToolUse", CopilotProtocol)
        assert hook.model_dump() == {
            **_COPILOT_ENVELOPE,
            "hookName": "PreToolUse",
            "preToolUse": {"toolName": "example_tool", "parameters": {}},
        }

    def test_post_tool_use(self) -> None:
        hook = _parse("copilot", "PostToolUse", CopilotProtocol)
        assert hook.model_dump() == {
            **_COPILOT_ENVELOPE,
            "hookName": "PostToolUse",
            "postToolUse": {
                "toolName": "example_tool",
                "parameters": {},
                "success": True,
                "executionTimeMs": 0,
                "result": None,
            },
        }

    def test_task_start(self) -> None:
        hook = _parse("copilot", "TaskStart", CopilotProtocol)
        assert hook.model_dump() == {
            **_COPILOT_ENVELOPE,
            "hookName": "TaskStart",
            "taskStart": {"task": "", "source": "startup"},
        }

    def test_user_prompt_submit(self) -> None:
        hook = _parse("copilot", "UserPromptSubmit", CopilotProtocol)
        assert hook.model_dump() == {
            **_COPILOT_ENVELOPE,
            "hookName": "UserPromptSubmit",
            "userPromptSubmit": {"userMessage": "Add a new test for the parser."},
        }

    def test_stop(self) -> None:
        hook = _parse("copilot", "Stop", CopilotProtocol)
        assert hook.model_dump() == {
            **_COPILOT_ENVELOPE,
            "hookName": "Stop",
            "stop": {"stopHookActive": False},
        }

    def test_pre_compact(self) -> None:
        hook = _parse("copilot", "PreCompact", CopilotProtocol)
        assert hook.model_dump() == {
            **_COPILOT_ENVELOPE,
            "hookName": "PreCompact",
            "preCompact": {"conversationLength": 10, "estimatedTokens": 1000},
        }

    def test_pre_tool_use_bash_inherits_claude_code_tool_map(self) -> None:
        hook = _parse("copilot", "tools/Bash", CopilotProtocol)
        assert hook.model_dump() == {
            **_COPILOT_ENVELOPE,
            "hookName": "PreToolUse",
            "preToolUse": {
                "toolName": "execute_command",
                "parameters": {"command": "ls -la"},
            },
        }

    def test_pre_compact_session_id_falls_back_to_cwd_hash(self) -> None:
        hook = _parse(
            "copilot", "PreCompact", CopilotProtocol, overrides={"session_id": ""}
        )
        expected_task_id = hashlib.sha256(b"/home/user/project").hexdigest()[:16]
        assert hook.model_dump() == {
            **_COPILOT_ENVELOPE,
            "taskId": expected_task_id,
            "hookName": "PreCompact",
            "preCompact": {"conversationLength": 10, "estimatedTokens": 1000},
        }


class TestCodexNormalisation:
    @pytest.mark.parametrize(
        "name",
        [
            "PreToolUse",
            "PostToolUse",
            "TaskStart",
            "UserPromptSubmit",
            "Stop",
            "tools/Read",
            "tools/Edit",
            "tools/Write",
            "tools/Mcp",
        ],
    )
    def test_matches_claude_code_normalisation(self, name: str) -> None:
        assert (
            _parse("claude-code", name, CodexProtocol).model_dump()
            == _parse("claude-code", name, ClaudeCodeProtocol).model_dump()
        )

    def test_pre_tool_use_concrete_value(self) -> None:
        hook = _parse("claude-code", "PreToolUse", CodexProtocol)
        assert hook.model_dump() == {
            **_CLAUDE_CODE_ENVELOPE,
            "hookName": "PreToolUse",
            "preToolUse": {
                "toolName": "execute_command",
                "parameters": {"command": "ls -la"},
            },
        }


class TestFrontendAsymmetries:
    def test_kiro_omits_read_path_where_claude_code_always_emits_it(self) -> None:
        kiro_hook = _parse("kiro", "tools/Grep", KiroProtocol)
        assert isinstance(kiro_hook, HookInputPreToolUse)
        assert kiro_hook.preToolUse is not None
        assert kiro_hook.preToolUse.parameters == {}
        assert "path" not in kiro_hook.preToolUse.parameters

        claude_code_hook = _parse(
            "claude-code",
            "tools/Read",
            ClaudeCodeProtocol,
            overrides={"tool_input": {}},
        )
        assert isinstance(claude_code_hook, HookInputPreToolUse)
        assert claude_code_hook.preToolUse is not None
        assert claude_code_hook.preToolUse.parameters == {"path": ""}
        assert "path" in claude_code_hook.preToolUse.parameters

    def test_kiro_shell_parameters_pass_through_where_claude_code_drops_unknown_keys(
        self,
    ) -> None:
        kiro_hook = _parse("kiro", "tools/Shell", KiroProtocol)
        assert isinstance(kiro_hook, HookInputPreToolUse)
        assert kiro_hook.preToolUse is not None
        assert kiro_hook.preToolUse.parameters == {
            "command": "ls -la",
            "summary": "list files",
        }

        claude_code_hook = _parse("claude-code", "PreToolUse", ClaudeCodeProtocol)
        assert isinstance(claude_code_hook, HookInputPreToolUse)
        assert claude_code_hook.preToolUse is not None
        assert claude_code_hook.preToolUse.parameters == {"command": "ls -la"}

    def test_cline_native_duration_normalises_where_kiro_payload_carries_none(
        self,
    ) -> None:
        cline_hook = _parse("cline", "PostToolUse", ClineProtocol)
        assert isinstance(cline_hook, HookInputPostToolUse)
        assert cline_hook.postToolUse is not None
        assert cline_hook.postToolUse.executionTimeMs == 42

        kiro_hook = _parse("kiro", "PostToolUse", KiroProtocol)
        assert isinstance(kiro_hook, HookInputPostToolUse)
        assert kiro_hook.postToolUse is not None
        assert kiro_hook.postToolUse.executionTimeMs == 0

    def test_kiro_tool_response_result_normalises_where_claude_code_has_no_result_key(
        self,
    ) -> None:
        kiro_hook = _parse("kiro", "PostToolUse", KiroProtocol)
        assert isinstance(kiro_hook, HookInputPostToolUse)
        assert kiro_hook.postToolUse is not None
        assert kiro_hook.postToolUse.result == "file1\nfile2"

        claude_code_hook = _parse("claude-code", "PostToolUse", ClaudeCodeProtocol)
        assert isinstance(claude_code_hook, HookInputPostToolUse)
        assert claude_code_hook.postToolUse is not None
        assert claude_code_hook.postToolUse.result is None
