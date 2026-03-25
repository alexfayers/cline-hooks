from __future__ import annotations

import cline_hooks.skill_tracker as module
from cline_hooks.skill_tracker import (
    is_skill_called,
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
