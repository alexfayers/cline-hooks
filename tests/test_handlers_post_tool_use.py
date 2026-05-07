from __future__ import annotations

import json
from typing import cast
from unittest.mock import patch

from cline_hooks.core.models import HookInputPostToolUse
from cline_hooks.frontends.cline import parse_cline_data as parse_data
from cline_hooks.handlers.post_tool_use import (
    handle_post_tool_use,
)

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


class TestHandlePostToolUse:
    def test_failed_tool_fires_persist_reminder(self) -> None:
        hook = _make_hook("replace_in_file", success=False)
        result = _run(hook)
        assert result is not None
        context = str(result.get("contextModification", ""))
        assert "failed" in context.lower()
        assert "persist" in context.lower()

    def test_build_failed_triggers_alert(self) -> None:
        hook = _make_hook("execute_command", result="BUILD FAILED: something went wrong")
        result = _run(hook)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "FAILED" in context


class TestSkillDetectionViaRead:
    def test_skill_md_read_records_skill(self) -> None:
        hook = _make_hook("read_file", parameters={"path": "/home/user/.kiro/skills/git-usage/SKILL.md"})
        with patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "git-usage")

    def test_non_skill_read_does_not_record(self) -> None:
        hook = _make_hook("read_file", parameters={"path": "/home/user/project/README.md"})
        with patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_record:
            _run(hook)
        mock_record.assert_not_called()

    def test_skill_md_in_nested_path(self) -> None:
        hook = _make_hook("read_file", parameters={"path": "/deep/nested/skills/pre-implementation/SKILL.md"})
        with patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "pre-implementation")

    def test_empty_path_does_not_record(self) -> None:
        hook = _make_hook("read_file", parameters={})
        with patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_record:
            _run(hook)
        mock_record.assert_not_called()
