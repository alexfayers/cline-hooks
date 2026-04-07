from __future__ import annotations

import json
from typing import cast
from unittest.mock import patch

import pytest

from cline_hooks.frontends.cline import parse_cline_data as parse_data
import cline_hooks.handlers.post_tool_use as module
from cline_hooks.handlers.post_tool_use import (
    _MEMORY_REMINDER_CHANCE,
    _MEMORY_TOOL_NAMES,
    _memory_chance,
    handle_post_tool_use,
)
import cline_hooks.memory_tracker as memory_tracker_module
from cline_hooks.models import HookInputPostToolUse

_BASE = {
    "clineVersion": "1.0",
    "timestamp": "2024-01-01T00:00:00Z",
    "taskId": "task-1",
    "userId": "user-1",
    "workspaceRoots": ["/workspace"],
    "hookName": "PostToolUse",
}


def _make_hook(
    tool_name: str,
    success: bool = True,
    result: str | None = None,
    parameters: dict[str, object] | None = None,
) -> HookInputPostToolUse:
    data = {
        **_BASE,
        "postToolUse": {
            "toolName": tool_name,
            "parameters": parameters or {},
            "success": success,
            "executionTimeMs": 10,
            "result": result,
        },
    }
    hook = parse_data(json.dumps(data))
    assert isinstance(hook, HookInputPostToolUse)
    return hook


def _run(hook: HookInputPostToolUse) -> dict[str, object] | None:
    output: list[str] = []
    try:
        with patch("builtins.print", side_effect=lambda s, **kw: output.append(s)):
            handle_post_tool_use(hook)
    except SystemExit:
        pass
    if not output:
        return None
    return cast("dict[str, object]", json.loads(output[0]))


@pytest.fixture(autouse=True)
def reset_memory_state() -> None:
    _memory_chance.chance = _MEMORY_REMINDER_CHANCE


class TestMemoryChanceFunctions:
    def test_reset_sets_to_zero(self) -> None:
        _memory_chance.reset()
        assert _memory_chance.chance == pytest.approx(0.0)

    def test_step_increments_by_fraction(self) -> None:
        _memory_chance.reset()
        _memory_chance.step()
        expected = _MEMORY_REMINDER_CHANCE / module._MEMORY_COOLDOWN_STEPS
        assert _memory_chance.chance == pytest.approx(expected)

    def test_step_caps_at_max(self) -> None:
        _memory_chance.chance = _MEMORY_REMINDER_CHANCE
        _memory_chance.step()
        assert _memory_chance.chance == pytest.approx(_MEMORY_REMINDER_CHANCE)

    def test_full_recovery_after_cooldown_steps(self) -> None:
        _memory_chance.reset()
        for _ in range(module._MEMORY_COOLDOWN_STEPS):
            _memory_chance.step()
        assert _memory_chance.chance == pytest.approx(_MEMORY_REMINDER_CHANCE)


class TestMemoryToolResetsChance:
    def test_memory_mcp_tool_resets_chance(self) -> None:
        for tool_name in _MEMORY_TOOL_NAMES:
            _memory_chance.chance = _MEMORY_REMINDER_CHANCE
            hook = _make_hook(
                "use_mcp_tool",
                parameters={
                    "server_name": "memory",
                    "tool_name": tool_name,
                    "arguments": {},
                },
            )
            _run(hook)
            assert _memory_chance.chance == pytest.approx(0.0), f"Expected reset for {tool_name}"

    def test_non_memory_mcp_tool_does_not_reset(self) -> None:
        _memory_chance.chance = _MEMORY_REMINDER_CHANCE
        hook = _make_hook(
            "use_mcp_tool",
            parameters={
                "server_name": "other",
                "tool_name": "some_tool",
                "arguments": {},
            },
        )
        _run(hook)
        assert _memory_chance.chance == pytest.approx(_MEMORY_REMINDER_CHANCE)


class TestHandlePostToolUse:
    def test_failed_tool_produces_no_output(self) -> None:
        hook = _make_hook("replace_in_file", success=False)
        result = _run(hook)
        assert result is None

    def test_build_failed_triggers_alert(self) -> None:
        _memory_chance.chance = 0.0
        hook = _make_hook("execute_command", result="BUILD FAILED: something went wrong")
        with patch("cline_hooks.handlers.post_tool_use.random.random", return_value=1.0):
            result = _run(hook)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "FAILED" in context

    def test_memory_reminder_fires_when_chance_is_max(self) -> None:
        _memory_chance.chance = _MEMORY_REMINDER_CHANCE
        hook = _make_hook("replace_in_file")
        with patch("cline_hooks.handlers.post_tool_use.random.random", return_value=0.0):
            result = _run(hook)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "MEMORY UPDATE REQUIRED" in context

    def test_memory_reminder_resets_chance_after_firing(self) -> None:
        _memory_chance.chance = _MEMORY_REMINDER_CHANCE
        hook = _make_hook("replace_in_file")
        with patch("cline_hooks.handlers.post_tool_use.random.random", return_value=0.0):
            _run(hook)
        assert _memory_chance.chance == pytest.approx(0.0)

    def test_memory_reminder_suppressed_after_reset(self) -> None:
        _memory_chance.chance = 0.0
        hook = _make_hook("replace_in_file")
        one_step = _MEMORY_REMINDER_CHANCE / module._MEMORY_COOLDOWN_STEPS
        with patch(
            "cline_hooks.handlers.post_tool_use.random.random",
            return_value=one_step + 0.01,
        ):
            result = _run(hook)
        context = cast("str", (result or {}).get("contextModification", ""))
        assert "MEMORY UPDATE REQUIRED" not in context

    def test_step_called_for_file_editing_tools(self) -> None:
        _memory_chance.chance = 0.0
        hook = _make_hook("write_to_file")
        with patch("cline_hooks.handlers.post_tool_use.random.random", return_value=1.0):
            _run(hook)
        assert _memory_chance.chance == pytest.approx(_MEMORY_REMINDER_CHANCE / module._MEMORY_COOLDOWN_STEPS)


class TestMemoryTrackerIntegration:
    def test_every_tool_call_increments_counter(self) -> None:
        hook = _make_hook("replace_in_file")
        with patch("cline_hooks.handlers.post_tool_use.random.random", return_value=1.0):
            _run(hook)
        assert memory_tracker_module.should_block("task-1", threshold=1)

    def test_failed_tool_still_increments_counter(self) -> None:
        hook = _make_hook("replace_in_file", success=False)
        _run(hook)
        assert memory_tracker_module.should_block("task-1", threshold=1)

    def test_memory_write_mcp_resets_counter(self) -> None:
        for _ in range(10):
            memory_tracker_module.increment("task-1")
        hook = _make_hook(
            "use_mcp_tool",
            parameters={
                "server_name": "memory",
                "tool_name": "create_entities",
                "arguments": {},
            },
        )
        _run(hook)
        assert not memory_tracker_module.should_block("task-1")

    def test_read_graph_does_not_reset_counter(self) -> None:
        for _ in range(10):
            memory_tracker_module.increment("task-1")
        hook = _make_hook(
            "use_mcp_tool",
            parameters={
                "server_name": "memory",
                "tool_name": "read_graph",
                "arguments": {},
            },
        )
        _run(hook)
        assert memory_tracker_module.should_block("task-1")
