from __future__ import annotations

import json

from cline_hooks.frontends.cline import parse_cline_data as parse_data
from cline_hooks.models import (
    HookInput,
    HookInputPostToolUse,
    HookInputPreCompact,
    HookInputPreToolUse,
    HookInputTaskCancel,
    HookInputTaskComplete,
    HookInputTaskResume,
    HookInputTaskStart,
    HookInputUserPromptSubmit,
    _filter_fields,
    inheritors,
)

BASE_FIELDS = {
    "clineVersion": "1.0",
    "timestamp": "2024-01-01T00:00:00Z",
    "taskId": "task-1",
    "userId": "user-1",
    "workspaceRoots": ["/workspace"],
    "hookName": "TaskStart",
}


def _make_json(**extra: object) -> str:
    return json.dumps({**BASE_FIELDS, **extra})


class TestInheritors:
    def test_returns_all_subclasses(self) -> None:
        result = inheritors(HookInput)
        assert HookInputPreToolUse in result
        assert HookInputPostToolUse in result
        assert HookInputTaskStart in result
        assert HookInputTaskResume in result
        assert HookInputTaskCancel in result
        assert HookInputTaskComplete in result
        assert HookInputUserPromptSubmit in result
        assert HookInputPreCompact in result

    def test_does_not_include_base(self) -> None:
        assert HookInput not in inheritors(HookInput)

    def test_empty_for_leaf_class(self) -> None:
        assert inheritors(HookInputPreCompact) == set()


class TestFilterFields:
    def test_keeps_known_fields(self) -> None:
        data = {
            "hookName": "TaskStart",
            "taskId": "id",
            "unknown": "drop",
        }
        result = _filter_fields(HookInput, data)
        assert "hookName" in result
        assert "taskId" in result
        assert "unknown" not in result

    def test_empty_data(self) -> None:
        assert _filter_fields(HookInput, {}) == {}


class TestParseData:
    def test_parses_task_start(self) -> None:
        result = parse_data(_make_json(hookName="TaskStart"))
        assert isinstance(result, HookInputTaskStart)

    def test_parses_task_resume(self) -> None:
        result = parse_data(_make_json(hookName="TaskResume"))
        assert isinstance(result, HookInputTaskResume)

    def test_parses_task_cancel(self) -> None:
        result = parse_data(_make_json(hookName="TaskCancel"))
        assert isinstance(result, HookInputTaskCancel)

    def test_parses_task_complete(self) -> None:
        result = parse_data(_make_json(hookName="TaskComplete"))
        assert isinstance(result, HookInputTaskComplete)

    def test_parses_pre_tool_use(self) -> None:
        result = parse_data(
            _make_json(
                hookName="PreToolUse",
                preToolUse={"toolName": "execute_command", "parameters": {}},
            )
        )
        assert isinstance(result, HookInputPreToolUse)
        assert result.preToolUse is not None
        assert result.preToolUse.toolName == "execute_command"

    def test_parses_post_tool_use(self) -> None:
        result = parse_data(
            _make_json(
                hookName="PostToolUse",
                postToolUse={
                    "toolName": "execute_command",
                    "parameters": {},
                    "success": True,
                    "executionTimeMs": 100,
                },
            )
        )
        assert isinstance(result, HookInputPostToolUse)

    def test_parses_pre_compact(self) -> None:
        result = parse_data(
            _make_json(
                hookName="PreCompact",
                preCompact={"conversationLength": 50, "estimatedTokens": 10000},
            )
        )
        assert isinstance(result, HookInputPreCompact)
        assert result.preCompact is not None
        assert result.preCompact.conversationLength == 50

    def test_unknown_hook_falls_back_to_base(self) -> None:
        result = parse_data(_make_json(hookName="UnknownHook"))
        assert type(result) is HookInput

    def test_unknown_fields_are_ignored(self) -> None:
        result = parse_data(_make_json(hookName="TaskStart", futureField="ignored"))
        assert isinstance(result, HookInputTaskStart)

    def test_task_start_empty_dict_defaults_task(self) -> None:
        result = parse_data(_make_json(hookName="TaskStart", taskStart={}))
        assert isinstance(result, HookInputTaskStart)
        assert result.taskStart is not None
        assert result.taskStart.task == ""

    def test_task_start_unknown_only_dict_defaults_task(self) -> None:
        result = parse_data(_make_json(hookName="TaskStart", taskStart={"taskMetadata": {}}))
        assert isinstance(result, HookInputTaskStart)
        assert result.taskStart is not None
        assert result.taskStart.task == ""

    def test_task_start_with_task_field(self) -> None:
        result = parse_data(_make_json(hookName="TaskStart", taskStart={"task": "do something"}))
        assert isinstance(result, HookInputTaskStart)
        assert result.taskStart is not None
        assert result.taskStart.task == "do something"

    def test_task_resume_empty_dict_defaults_task(self) -> None:
        result = parse_data(_make_json(hookName="TaskResume", taskResume={}))
        assert isinstance(result, HookInputTaskResume)
        assert result.taskResume is not None
        assert result.taskResume.task == ""

    def test_fields_populated_correctly(self) -> None:
        result = parse_data(_make_json(hookName="TaskStart"))
        assert result.taskId == "task-1"
        assert result.workspaceRoots == ["/workspace"]
