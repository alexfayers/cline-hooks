from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.plugin import HookResult
from cline_hooks.core.vocabulary import CanonicalHook, PluginScope
from cline_hooks.plugins.delegation import DelegationPlugin
from cline_hooks.state.agents import record_agent_use

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_TASK = "task-1"
_ENABLED_ENV = {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"}


def _enable(mocker: MockerFixture) -> None:
    mocker.patch.dict("os.environ", _ENABLED_ENV, clear=True)


def _disable(mocker: MockerFixture) -> None:
    mocker.patch.dict("os.environ", {}, clear=True)


def _pre_tool_use(tool_name: str, *, agent_type: str = "") -> dict[str, object]:
    return {
        "task_id": _TASK,
        "tool_name": tool_name,
        "parameters": {},
        "workspace_roots": [],
        "agent_type": agent_type,
    }


def _pre_shell(command: str, *, agent_type: str = "") -> dict[str, object]:
    return {
        "task_id": _TASK,
        "tool_name": "execute_command",
        "command": command,
        "workspace_roots": [],
        "agent_type": agent_type,
    }


class TestFileEditTools:
    def test_fires_on_edit(self, mocker: MockerFixture) -> None:
        _enable(mocker)
        result = DelegationPlugin().on_hook(
            CanonicalHook.PRE_TOOL_USE, **_pre_tool_use("replace_in_file")
        )
        assert isinstance(result, HookResult)
        assert result.notes

    def test_fires_on_write(self, mocker: MockerFixture) -> None:
        _enable(mocker)
        result = DelegationPlugin().on_hook(
            CanonicalHook.PRE_TOOL_USE, **_pre_tool_use("write_to_file")
        )
        assert isinstance(result, HookResult)
        assert result.notes

    def test_silent_when_env_var_unset(self, mocker: MockerFixture) -> None:
        _disable(mocker)
        result = DelegationPlugin().on_hook(
            CanonicalHook.PRE_TOOL_USE, **_pre_tool_use("replace_in_file")
        )
        assert result is None

    def test_silent_for_subagent(self, mocker: MockerFixture) -> None:
        _enable(mocker)
        result = DelegationPlugin().on_hook(
            CanonicalHook.PRE_TOOL_USE,
            **_pre_tool_use("replace_in_file", agent_type="Explore"),
        )
        assert result is None

    def test_silent_after_agent_recorded(self, mocker: MockerFixture) -> None:
        _enable(mocker)
        record_agent_use(_TASK, "Agent")
        result = DelegationPlugin().on_hook(
            CanonicalHook.PRE_TOOL_USE, **_pre_tool_use("replace_in_file")
        )
        assert result is None

    def test_fires_only_once_per_session(self, mocker: MockerFixture) -> None:
        _enable(mocker)
        first = DelegationPlugin().on_hook(
            CanonicalHook.PRE_TOOL_USE, **_pre_tool_use("replace_in_file")
        )
        second = DelegationPlugin().on_hook(
            CanonicalHook.PRE_TOOL_USE, **_pre_tool_use("write_to_file")
        )
        assert first is not None
        assert first.notes
        assert second is None


class TestShellCommands:
    @pytest.mark.parametrize(
        "command",
        ["ls -la", "git status", "rg foo", "ls && git log", ""],
    )
    def test_silent_for_read_only_or_empty_command(
        self, mocker: MockerFixture, command: str
    ) -> None:
        _enable(mocker)
        result = DelegationPlugin().on_hook(
            PluginScope.PRE_SHELL, **_pre_shell(command)
        )
        assert result is None

    @pytest.mark.parametrize(
        "command",
        [
            "pytest",
            "npm run build",
            "sed -i s/a/b/ f",
            "echo x > f",
            "git commit -m x",
            "ls && rm y",
        ],
    )
    def test_fires_for_mutating_command(
        self, mocker: MockerFixture, command: str
    ) -> None:
        _enable(mocker)
        result = DelegationPlugin().on_hook(
            PluginScope.PRE_SHELL, **_pre_shell(command)
        )
        assert isinstance(result, HookResult)
        assert result.notes
