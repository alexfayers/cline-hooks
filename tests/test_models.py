from __future__ import annotations

import json
from typing import get_args

from cline_hooks.core.models import (
    HOOK_INPUTS,
    HookFields,
    HookInput,
    HookInputPostToolUse,
    HookInputPreCompact,
    HookInputPreToolUse,
    HookInputStop,
    HookInputTaskCancel,
    HookInputTaskComplete,
    HookInputTaskResume,
    HookInputTaskStart,
)
from cline_hooks.core.protocol import RawPayload
from cline_hooks.core.vocabulary import CanonicalHook
from cline_hooks.frontends.cline import ClineProtocol


def parse_data(raw: str) -> HookInput:
    return ClineProtocol().parse(RawPayload.from_stdin(raw))


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


class TestHookInputsTable:
    def test_covers_every_canonical_hook(self) -> None:
        for canonical_hook in CanonicalHook:
            assert canonical_hook in HOOK_INPUTS

    def test_entries_are_self_consistent(self) -> None:
        for canonical_hook, input_cls in HOOK_INPUTS.items():
            assert issubclass(input_cls, HookInput)
            assert input_cls.model_fields["hookName"].default == canonical_hook
            payload_field_info = input_cls.model_fields[input_cls.payload_field]
            candidates = get_args(payload_field_info.annotation) or (payload_field_info.annotation,)
            assert any(isinstance(candidate, type) and issubclass(candidate, HookFields) for candidate in candidates)


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

    def test_parses_stop(self) -> None:
        result = parse_data(_make_json(hookName="Stop", stop={"stopHookActive": True}))
        assert isinstance(result, HookInputStop)
        assert result.stop is not None
        assert result.stop.stopHookActive is True

    def test_stop_empty_dict_defaults_false(self) -> None:
        result = parse_data(_make_json(hookName="Stop", stop={}))
        assert isinstance(result, HookInputStop)
        assert result.stop is not None
        assert result.stop.stopHookActive is False

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
