from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from cline_hooks.core.models import (
    HookInputTaskCancel,
    HookInputTaskComplete,
    HookInputTaskResume,
    HookInputTaskStart,
    TaskStartFields,
)
from cline_hooks.core.plugin import HooksPlugin, ToolingNote
from cline_hooks.handlers.git_context import get_generic_tooling_note, resolve_tooling_notes
from cline_hooks.handlers.task_lifecycle import (
    _format_block_history,
    _get_dirty_count,
    handle_task_cancel,
    handle_task_complete,
    handle_task_resume,
    handle_task_start,
)
from cline_hooks.state.agents import has_agent_use, record_agent_use
from cline_hooks.state.context import should_nudge_context
from cline_hooks.state.memory import has_memory_writes, record_memory_write
from cline_hooks.state.plan import consume_plan_nudge, record_plan_exit
from cline_hooks.state.skills import is_skill_called, record_skill
from cline_hooks.state.store import TaskBlockEvent, TaskStateStore
from cline_hooks.state.turns import increment
from cline_hooks.state.workspace import record_workspace, should_note_workspace_change

BASE = {
    "clineVersion": "1.0",
    "timestamp": "2024-01-01T00:00:00Z",
    "taskId": "task-1",
    "userId": "user-1",
    "workspaceRoots": ["/workspace"],
    "model": None,
}


def _task_start(roots: list[str] | None = None, source: str = "", agent_type: str = "") -> HookInputTaskStart:
    return HookInputTaskStart(
        taskId="task-1",
        workspaceRoots=roots or ["/workspace"],
        hookName="TaskStart",
        taskStart=TaskStartFields(source=source),
        agentType=agent_type,
    )


def _task_resume(roots: list[str] | None = None) -> HookInputTaskResume:
    return HookInputTaskResume(
        taskId="task-1",
        workspaceRoots=roots or ["/workspace"],
        hookName="TaskResume",
    )


def _task_cancel(roots: list[str] | None = None) -> HookInputTaskCancel:
    return HookInputTaskCancel(
        taskId="task-1",
        workspaceRoots=roots or ["/workspace"],
        hookName="TaskCancel",
    )


def _task_complete(roots: list[str] | None = None) -> HookInputTaskComplete:
    return HookInputTaskComplete(
        taskId="task-1",
        workspaceRoots=roots or ["/workspace"],
        hookName="TaskComplete",
    )


def _capture_output(hook_fn, hook_input):
    """Run a handler and capture its stdout JSON output."""
    captured: list[str] = []
    with patch("sys.stdout") as mock_stdout:
        mock_stdout.write = captured.append
        with pytest.raises(SystemExit):
            hook_fn(hook_input)
    return captured


class TestFormatBlockHistory:
    def test_includes_header(self) -> None:
        blocks = [TaskBlockEvent("tool", "reason", "2024-01-01T00:00:00Z")]
        result = _format_block_history(blocks)
        assert "previously interrupted" in result

    def test_includes_each_block(self) -> None:
        blocks = [
            TaskBlockEvent("tool-a", "reason A", "2024-01-01T00:00:00Z"),
            TaskBlockEvent("tool-b", "reason B", "2024-01-01T01:00:00Z"),
        ]
        result = _format_block_history(blocks)
        assert "tool-a" in result
        assert "reason B" in result


class TestGetDirtyCount:
    def test_returns_count_from_valid_repo(self, tmp_path: Path) -> None:
        mock_repo = MagicMock()
        mock_repo.index.diff.return_value = [1, 2]
        mock_repo.untracked_files = ["file.txt"]
        with patch("cline_hooks.handlers.task_lifecycle.git.Repo", return_value=mock_repo):
            assert _get_dirty_count([str(tmp_path)]) == 3

    def test_returns_none_for_invalid_repo(self, tmp_path: Path) -> None:
        import git.exc

        with patch(
            "cline_hooks.handlers.task_lifecycle.git.Repo",
            side_effect=git.exc.InvalidGitRepositoryError,
        ):
            assert _get_dirty_count([str(tmp_path)]) is None

    def test_returns_none_for_empty_roots(self) -> None:
        assert _get_dirty_count([]) is None


class TestGetGenericToolingNote:
    def test_python_project_with_uv(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("")
        with patch("cline_hooks.handlers.git_context.shutil.which", return_value="/usr/bin/uv"):
            note = get_generic_tooling_note([str(tmp_path)])
        assert note is not None
        assert "uv" in note
        assert "Python project" in note

    def test_python_project_without_uv(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("")
        with patch("cline_hooks.handlers.git_context.shutil.which", return_value=None):
            note = get_generic_tooling_note([str(tmp_path)])
        assert note is not None
        assert "Python project" in note
        assert "uv" not in note

    def test_no_marker_returns_none(self, tmp_path: Path) -> None:
        assert get_generic_tooling_note([str(tmp_path)]) is None

    def test_first_qualifying_root_wins(self, tmp_path: Path) -> None:
        first = tmp_path / "first"
        second = tmp_path / "second"
        first.mkdir()
        second.mkdir()
        (second / "pyproject.toml").write_text("")
        with patch("cline_hooks.handlers.git_context.shutil.which", return_value=None):
            note = get_generic_tooling_note([str(first), str(second)])
        assert note is not None
        assert "Python project" in note


class _ReplacingPlugin(HooksPlugin):
    def get_tooling_note(self, workspace_roots: list[str]) -> ToolingNote | None:
        return ToolingNote(note="PLUGIN NOTE", replaces_generic=True)


class TestResolveToolingNotes:
    def test_returns_note_when_no_plugin_replaces(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("")
        assert resolve_tooling_notes([HooksPlugin()], [str(tmp_path)]) != []

    def test_returns_only_plugin_note_when_replaced(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("")
        assert resolve_tooling_notes([_ReplacingPlugin()], [str(tmp_path)]) == ["PLUGIN NOTE"]

    def test_returns_empty_when_nothing_matches(self, tmp_path: Path) -> None:
        assert resolve_tooling_notes([], [str(tmp_path)]) == []

    def test_empty_plugin_list_still_returns_note(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("")
        assert resolve_tooling_notes([], [str(tmp_path)]) != []


class TestHandleTaskStart:
    def _run(self, hook: HookInputTaskStart) -> dict[str, object]:
        output: list[str] = []
        with (
            patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
            pytest.raises(SystemExit),
        ):
            handle_task_start(hook)
        return cast("dict[str, object]", json.loads(output[0]))

    def test_git_context_included_when_present(self, tmp_path: Path) -> None:
        with patch(
            "cline_hooks.handlers.task_lifecycle.get_git_context",
            return_value="Branch: main",
        ):
            result = self._run(_task_start([str(tmp_path)]))
        assert "Branch: main" in cast("str", result["contextModification"])

    def test_cancel_is_false(self, tmp_path: Path) -> None:
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            result = self._run(_task_start([str(tmp_path)]))
        assert result["cancel"] is False

    def test_agent_use_reset_on_start(self, tmp_path: Path) -> None:
        record_agent_use("task-1", "Agent")
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)]))
        assert not has_agent_use("task-1")

    def test_context_band_reset_on_start(self, tmp_path: Path) -> None:
        should_nudge_context("task-1", 210_000)
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)]))
        assert should_nudge_context("task-1", 210_000) is True

    def test_plan_exit_reset_on_start(self, tmp_path: Path) -> None:
        record_plan_exit("task-1")
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)]))
        assert consume_plan_nudge("task-1") is False

    def test_skill_preserved_on_compact(self, tmp_path: Path) -> None:
        record_skill("task-1", "git-usage")
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)], source="compact"))
        assert is_skill_called("task-1", "git-usage")

    def test_memory_writes_preserved_on_compact(self, tmp_path: Path) -> None:
        record_memory_write("task-1", "create_entities")
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)], source="compact"))
        assert has_memory_writes("task-1")

    def test_agent_use_preserved_on_compact(self, tmp_path: Path) -> None:
        record_agent_use("task-1", "Agent")
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)], source="compact"))
        assert has_agent_use("task-1")

    def test_context_band_preserved_on_compact(self, tmp_path: Path) -> None:
        should_nudge_context("task-1", 210_000)
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)], source="compact"))
        assert should_nudge_context("task-1", 210_000) is False

    def test_turns_preserved_on_compact(self, tmp_path: Path) -> None:
        increment("task-1")
        increment("task-1")
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)], source="compact"))
        assert increment("task-1") == 3

    def test_skill_preserved_on_resume(self, tmp_path: Path) -> None:
        record_skill("task-1", "git-usage")
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)], source="resume"))
        assert is_skill_called("task-1", "git-usage")

    def test_skill_reset_on_startup(self, tmp_path: Path) -> None:
        record_skill("task-1", "git-usage")
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)], source="startup"))
        assert not is_skill_called("task-1", "git-usage")

    def test_git_context_emitted_on_compact(self, tmp_path: Path) -> None:
        with patch(
            "cline_hooks.handlers.task_lifecycle.get_git_context",
            return_value="Branch: main",
        ):
            result = self._run(_task_start([str(tmp_path)], source="compact"))
        assert "Branch: main" in cast("str", result["contextModification"])

    def test_tooling_note_included_when_unreplaced(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None),
            patch("cline_hooks.handlers.task_lifecycle.load_plugins", return_value=[HooksPlugin()]),
            patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"),
        ):
            result = self._run(_task_start([str(tmp_path)]))
        assert "TOOLING NOTE" in cast("str", result["contextModification"])

    def test_tooling_note_replaced_when_plugin_replaces(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None),
            patch("cline_hooks.handlers.task_lifecycle.load_plugins", return_value=[_ReplacingPlugin()]),
            patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"),
        ):
            result = self._run(_task_start([str(tmp_path)]))
        assert "TOOLING NOTE" not in cast("str", result["contextModification"])

    def test_workspace_state_seeded_on_start(self, tmp_path: Path) -> None:
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)]))
        assert should_note_workspace_change("task-1", [str(tmp_path)]) is False
        assert should_note_workspace_change("task-1", ["/other"]) is True

    def test_plugins_receive_source_on_start(self, tmp_path: Path) -> None:
        captured: dict[str, object] = {}

        class _CapturingPlugin(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> None:
                if hook_name == "TaskStart":
                    captured.update(kwargs)

        with (
            patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None),
            patch("cline_hooks.handlers.task_lifecycle.load_plugins", return_value=[_CapturingPlugin()]),
        ):
            self._run(_task_start([str(tmp_path)], source="compact"))
        assert captured.get("source") == "compact"

    def test_plugins_receive_agent_type_on_start(self, tmp_path: Path) -> None:
        captured: dict[str, object] = {}

        class _CapturingPlugin(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> None:
                if hook_name == "TaskStart":
                    captured.update(kwargs)

        with (
            patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None),
            patch("cline_hooks.handlers.task_lifecycle.load_plugins", return_value=[_CapturingPlugin()]),
        ):
            self._run(_task_start([str(tmp_path)], agent_type="Explore"))
        assert captured.get("agent_type") == "Explore"


class TestHandleTaskResume:
    def _run(self, hook: HookInputTaskResume, store: TaskStateStore | None = None) -> dict[str, object]:
        output: list[str] = []
        with (
            patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
            patch(
                "cline_hooks.handlers.task_lifecycle._store",
                store or TaskStateStore(Path("/nonexistent")),
            ),
            pytest.raises(SystemExit),
        ):
            handle_task_resume(hook)
        return cast("dict[str, object]", json.loads(output[0]))

    def test_block_history_included_when_present(self, tmp_path: Path) -> None:
        store = TaskStateStore(tmp_path / "state.json")
        store.record_block("task-1", "tool", "reason")
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            result = self._run(_task_resume([str(tmp_path)]), store=store)
        assert "interrupted" in cast("str", result["contextModification"])

    def test_no_block_history_when_none(self, tmp_path: Path) -> None:
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            result = self._run(_task_resume([str(tmp_path)]))
        assert "interrupted" not in cast("str", result["contextModification"])

    def test_skills_preserved_on_resume(self, tmp_path: Path) -> None:
        record_skill("task-1", "git-usage")
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            self._run(_task_resume([str(tmp_path)]))
        assert is_skill_called("task-1", "git-usage")

    def test_agent_use_preserved_on_resume(self, tmp_path: Path) -> None:
        record_agent_use("task-1", "Agent")
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            self._run(_task_resume([str(tmp_path)]))
        assert has_agent_use("task-1")

    def test_tooling_note_included_when_unreplaced(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None),
            patch("cline_hooks.handlers.task_lifecycle.load_plugins", return_value=[HooksPlugin()]),
            patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"),
        ):
            result = self._run(_task_resume([str(tmp_path)]))
        assert "TOOLING NOTE" in cast("str", result["contextModification"])

    def test_tooling_note_replaced_when_plugin_replaces(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None),
            patch("cline_hooks.handlers.task_lifecycle.load_plugins", return_value=[_ReplacingPlugin()]),
            patch("cline_hooks.handlers.git_context.get_generic_tooling_note", return_value="TOOLING NOTE"),
        ):
            result = self._run(_task_resume([str(tmp_path)]))
        assert "TOOLING NOTE" not in cast("str", result["contextModification"])

    def test_workspace_state_seeded_on_resume(self, tmp_path: Path) -> None:
        with patch("cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None):
            self._run(_task_resume([str(tmp_path)]))
        assert should_note_workspace_change("task-1", [str(tmp_path)]) is False
        assert should_note_workspace_change("task-1", ["/other"]) is True


class TestHandleTaskCancel:
    def _run(self, hook: HookInputTaskCancel, store: TaskStateStore | None = None) -> dict[str, object]:
        output: list[str] = []
        with (
            patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
            patch(
                "cline_hooks.handlers.task_lifecycle._store",
                store or TaskStateStore(Path("/nonexistent")),
            ),
            pytest.raises(SystemExit),
        ):
            handle_task_cancel(hook)
        return cast("dict[str, object]", json.loads(output[0]))

    def test_no_output_when_no_blocks(self, tmp_path: Path) -> None:
        result = self._run(_task_cancel([str(tmp_path)]))
        assert cast("str", result.get("contextModification", "")) == ""


class TestHandleTaskComplete:
    def _run(self, hook: HookInputTaskComplete, store: TaskStateStore | None = None) -> dict[str, object]:
        output: list[str] = []
        with (
            patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
            patch(
                "cline_hooks.handlers.task_lifecycle._store",
                store or TaskStateStore(Path("/nonexistent")),
            ),
            pytest.raises(SystemExit),
        ):
            handle_task_complete(hook)
        return cast("dict[str, object]", json.loads(output[0]))

    def test_clears_blocks_on_complete(self, tmp_path: Path) -> None:
        store = TaskStateStore(tmp_path / "state.json")
        store.record_block("task-1", "tool", "reason")
        import git.exc

        with patch(
            "cline_hooks.handlers.task_lifecycle.git.Repo",
            side_effect=git.exc.InvalidGitRepositoryError,
        ):
            self._run(_task_complete([str(tmp_path)]), store=store)
        assert store.get_blocks("task-1") == []

    def test_no_context_injected(self, tmp_path: Path) -> None:
        result = self._run(_task_complete([str(tmp_path)]))
        assert "contextModification" not in result

    def test_agent_use_reset_on_complete(self, tmp_path: Path) -> None:
        record_agent_use("task-1", "Agent")
        import git.exc

        with patch(
            "cline_hooks.handlers.task_lifecycle.git.Repo",
            side_effect=git.exc.InvalidGitRepositoryError,
        ):
            self._run(_task_complete([str(tmp_path)]))
        assert not has_agent_use("task-1")

    def test_context_band_reset_on_complete(self, tmp_path: Path) -> None:
        should_nudge_context("task-1", 210_000)
        self._run(_task_complete([str(tmp_path)]))
        assert should_nudge_context("task-1", 210_000) is True

    def test_plan_exit_reset_on_complete(self, tmp_path: Path) -> None:
        record_plan_exit("task-1")
        self._run(_task_complete([str(tmp_path)]))
        assert consume_plan_nudge("task-1") is False

    def test_workspace_state_reset_on_complete(self, tmp_path: Path) -> None:
        record_workspace("task-1", [str(tmp_path)])
        self._run(_task_complete([str(tmp_path)]))
        assert should_note_workspace_change("task-1", [str(tmp_path)]) is False
        assert should_note_workspace_change("task-1", ["/other"]) is True
