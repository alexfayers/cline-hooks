from __future__ import annotations

import json
from typing import cast
from unittest.mock import patch

from cline_hooks.core.models import HookInputPostToolUse
from cline_hooks.frontends.cline import parse_cline_data as parse_data
from cline_hooks.handlers.post_tool_use import (
    _is_session_end_skill,
    handle_post_tool_use,
)
from cline_hooks.state.memory import record_memory_write

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

    def test_claude_code_read_skill_detected(self) -> None:
        hook = _make_hook("Read", parameters={"file_path": "/Users/me/.claude/skills/git-usage/SKILL.md"})
        with patch("cline_hooks.handlers.post_tool_use._record_skill") as mock_record:
            _run(hook)
        mock_record.assert_called_once_with("task-1", "git-usage")


class TestIsSessionEndSkill:
    def test_claude_code_skill_tool(self) -> None:
        assert _is_session_end_skill("Skill", {"skill": "session-end"})

    def test_cline_use_skill(self) -> None:
        assert _is_session_end_skill("use_skill", {"skill_name": "session-end"})

    def test_read_skill_md(self) -> None:
        assert _is_session_end_skill("read_file", {"path": "/home/user/.kiro/skills/session-end/SKILL.md"})

    def test_claude_code_read_skill_md(self) -> None:
        assert _is_session_end_skill("Read", {"file_path": "/Users/me/.claude/skills/session-end/SKILL.md"})

    def test_other_skill_not_detected(self) -> None:
        assert not _is_session_end_skill("Skill", {"skill": "git-usage"})

    def test_unrelated_tool_not_detected(self) -> None:
        assert not _is_session_end_skill("Bash", {"command": "echo hi"})


class TestMemoryWarningOnSessionEnd:
    def test_warns_when_no_memory_writes(self) -> None:
        hook = _make_hook("Skill", parameters={"skill": "session-end"})
        result = _run(hook)
        assert result is not None
        context = str(result.get("contextModification", ""))
        assert "No memory writes" in context

    def test_no_warning_when_memory_written(self) -> None:
        record_memory_write("task-1", "create_entities")
        hook = _make_hook("Skill", parameters={"skill": "session-end"})
        result = _run(hook)
        if result is not None:
            context = str(result.get("contextModification", ""))
            assert "No memory writes" not in context

    def test_no_warning_for_non_session_end_skill(self) -> None:
        hook = _make_hook("Skill", parameters={"skill": "git-usage"})
        result = _run(hook)
        if result is not None:
            context = str(result.get("contextModification", ""))
            assert "No memory writes" not in context
