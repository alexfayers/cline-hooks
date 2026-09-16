from __future__ import annotations

import logging

import pytest

from cline_hooks.core.hook_kwargs import (
    PreShellKwargs,
    PreToolUseKwargs,
    ToolFailedKwargs,
    TrackToolUseKwargs,
)


class TestPreShellKwargs:
    def test_build_populates_documented_fields(self) -> None:
        built = PreShellKwargs.build(
            {
                "task_id": "t1",
                "tool_name": "execute_command",
                "command": "ls -la",
                "workspace_roots": ["/repo"],
                "agent_type": "Explore",
            }
        )
        assert built.task_id == "t1"
        assert built.tool_name == "execute_command"
        assert built.command == "ls -la"
        assert built.workspace_roots == ["/repo"]
        assert built.agent_type == "Explore"

    def test_missing_fields_default_empty(self) -> None:
        built = PreShellKwargs.build({})
        assert built.command == ""
        assert built.workspace_roots == []

    def test_unknown_kwargs_are_ignored(self) -> None:
        built = PreShellKwargs.build({"command": "ls", "mcp_tool_name": "x"})
        assert built.command == "ls"
        assert built.model_extra is None


class TestPreToolUseKwargs:
    def test_build_populates_documented_fields(self) -> None:
        built = PreToolUseKwargs.build(
            {
                "task_id": "t1",
                "tool_name": "replace_in_file",
                "parameters": {"path": "/x.py"},
                "workspace_roots": ["/repo"],
                "agent_type": "Explore",
            }
        )
        assert built.task_id == "t1"
        assert built.tool_name == "replace_in_file"
        assert built.parameters == {"path": "/x.py"}
        assert built.workspace_roots == ["/repo"]
        assert built.agent_type == "Explore"

    def test_missing_fields_default_empty(self) -> None:
        built = PreToolUseKwargs.build({})
        assert built.parameters == {}
        assert built.workspace_roots == []

    def test_unknown_kwargs_are_ignored(self) -> None:
        built = PreToolUseKwargs.build({"tool_name": "write_to_file", "command": "x"})
        assert built.tool_name == "write_to_file"
        assert built.model_extra is None


class TestTrackToolUseKwargs:
    def test_build_populates_documented_fields(self) -> None:
        built = TrackToolUseKwargs.build(
            {
                "task_id": "t1",
                "tool_name": "use_mcp_tool",
                "parameters": {"k": "v"},
                "is_state_write": True,
                "mcp_tool_name": "SomeTool",
                "workspace_roots": ["/repo"],
                "agent_type": "Explore",
            }
        )
        assert built.parameters == {"k": "v"}
        assert built.is_state_write is True
        assert built.mcp_tool_name == "SomeTool"
        assert built.workspace_roots == ["/repo"]
        assert built.agent_type == "Explore"

    def test_missing_fields_default(self) -> None:
        built = TrackToolUseKwargs.build({})
        assert built.parameters == {}
        assert built.is_state_write is False
        assert built.mcp_tool_name is None


class TestToolFailedKwargs:
    def test_build_populates_documented_fields(self) -> None:
        built = ToolFailedKwargs.build(
            {
                "task_id": "t1",
                "tool_name": "execute_command",
                "parameters": {"command": "boom"},
                "workspace_roots": ["/repo"],
                "agent_type": "Explore",
            }
        )
        assert built.tool_name == "execute_command"
        assert built.parameters == {"command": "boom"}
        assert built.workspace_roots == ["/repo"]
        assert built.agent_type == "Explore"


class TestFailOpen:
    def test_malformed_known_field_keeps_raw_value_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            built = TrackToolUseKwargs.build({"task_id": 123})
        assert built.task_id == 123  # type: ignore[comparison-overlap]
        assert "Invalid TrackToolUseKwargs kwargs" in caplog.text
