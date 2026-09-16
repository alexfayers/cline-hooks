from __future__ import annotations

import cline_hooks.state.skills as module
from cline_hooks.state.skills import (
    is_session_end_skill,
    is_skill_called,
    is_wrap_up_skill,
    record_skill,
    required_skill_for,
    reset,
)

_TASK = "task-1"


class TestRecordAndCheck:
    def test_skill_not_called_initially(self) -> None:
        assert not is_skill_called(_TASK, "git-usage")

    def test_record_marks_skill_as_called(self) -> None:
        record_skill(_TASK, "git-usage")
        assert is_skill_called(_TASK, "git-usage")

    def test_multiple_skills_tracked_independently(self) -> None:
        record_skill(_TASK, "git-usage")
        assert is_skill_called(_TASK, "git-usage")
        assert not is_skill_called(_TASK, "cr")

    def test_reset_clears_skills_for_task(self) -> None:
        record_skill(_TASK, "git-usage")
        record_skill(_TASK, "cr")
        reset(_TASK)
        assert not is_skill_called(_TASK, "git-usage")
        assert not is_skill_called(_TASK, "cr")

    def test_reset_does_not_affect_other_tasks(self) -> None:
        record_skill(_TASK, "git-usage")
        record_skill("other-task", "git-usage")
        reset(_TASK)
        assert is_skill_called("other-task", "git-usage")

    def test_skills_isolated_per_task(self) -> None:
        record_skill(_TASK, "git-usage")
        assert not is_skill_called("other-task", "git-usage")

    def test_persists_across_reads(self) -> None:
        record_skill(_TASK, "git-usage")
        assert is_skill_called(_TASK, "git-usage")
        assert is_skill_called(_TASK, "git-usage")


class TestIsSessionEndSkill:
    def test_use_skill_with_skill_key(self) -> None:
        assert is_session_end_skill("use_skill", {"skill": "session-end"})

    def test_cline_use_skill(self) -> None:
        assert is_session_end_skill("use_skill", {"skill_name": "session-end"})

    def test_read_skill_md(self) -> None:
        assert is_session_end_skill(
            "read_file", {"path": "/home/user/.kiro/skills/session-end/SKILL.md"}
        )

    def test_other_skill_not_detected(self) -> None:
        assert not is_session_end_skill("use_skill", {"skill": "git-usage"})

    def test_unrelated_tool_not_detected(self) -> None:
        assert not is_session_end_skill("execute_command", {"command": "echo hi"})


class TestIsWrapUpSkill:
    def test_session_end_is_wrap_up(self) -> None:
        assert is_wrap_up_skill("use_skill", {"skill": "session-end"})

    def test_handoff_is_wrap_up(self) -> None:
        assert is_wrap_up_skill("use_skill", {"skill": "handoff"})

    def test_handoff_via_read(self) -> None:
        assert is_wrap_up_skill(
            "read_file", {"path": "/Users/me/.claude/skills/handoff/SKILL.md"}
        )

    def test_unrelated_skill_not_wrap_up(self) -> None:
        assert not is_wrap_up_skill("use_skill", {"skill": "git-usage"})

    def test_unrelated_tool_not_wrap_up(self) -> None:
        assert not is_wrap_up_skill("execute_command", {"command": "echo hi"})


class TestRequiredSkillFor:
    def test_git_command_requires_git_usage(self) -> None:
        assert required_skill_for(["git"]) == "git-usage"

    def test_cr_command_requires_cr_skill(self) -> None:
        assert required_skill_for(["cr"]) == "cr"

    def test_unrelated_command_returns_none(self) -> None:
        assert required_skill_for(["just"]) is None

    def test_empty_command_returns_none(self) -> None:
        assert required_skill_for([]) is None

    def test_path_containing_git_is_not_matched(self) -> None:
        assert required_skill_for(["pnpm"]) is None

    def test_all_requirements_covered(self) -> None:
        for trigger, skill in module._SKILL_REQUIREMENTS.items():
            assert required_skill_for([trigger]) == skill
