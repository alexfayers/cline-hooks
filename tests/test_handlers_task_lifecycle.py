from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from cline_hooks.handlers.task_lifecycle import (
    _format_block_history,
    _get_dirty_count,
    handle_task_cancel,
    handle_task_complete,
    handle_task_resume,
    handle_task_start,
)
from cline_hooks.skill_tracker import is_skill_called, record_skill
from cline_hooks.models import (
    HookInputTaskCancel,
    HookInputTaskComplete,
    HookInputTaskResume,
    HookInputTaskStart,
)
from cline_hooks.state import TaskBlockEvent, TaskStateStore

BASE = {
    "clineVersion": "1.0",
    "timestamp": "2024-01-01T00:00:00Z",
    "taskId": "task-1",
    "userId": "user-1",
    "workspaceRoots": ["/workspace"],
    "model": None,
}


def _task_start(roots: list[str] | None = None) -> HookInputTaskStart:
    return HookInputTaskStart(
        clineVersion="1.0",
        timestamp="2024-01-01T00:00:00Z",
        taskId="task-1",
        userId="user-1",
        workspaceRoots=roots or ["/workspace"],
        model=None,
        hookName="TaskStart",
    )


def _task_resume(roots: list[str] | None = None) -> HookInputTaskResume:
    return HookInputTaskResume(
        clineVersion="1.0",
        timestamp="2024-01-01T00:00:00Z",
        taskId="task-1",
        userId="user-1",
        workspaceRoots=roots or ["/workspace"],
        model=None,
        hookName="TaskResume",
    )


def _task_cancel(roots: list[str] | None = None) -> HookInputTaskCancel:
    return HookInputTaskCancel(
        clineVersion="1.0",
        timestamp="2024-01-01T00:00:00Z",
        taskId="task-1",
        userId="user-1",
        workspaceRoots=roots or ["/workspace"],
        model=None,
        hookName="TaskCancel",
    )


def _task_complete(roots: list[str] | None = None) -> HookInputTaskComplete:
    return HookInputTaskComplete(
        clineVersion="1.0",
        timestamp="2024-01-01T00:00:00Z",
        taskId="task-1",
        userId="user-1",
        workspaceRoots=roots or ["/workspace"],
        model=None,
        hookName="TaskComplete",
    )


def _capture_output(hook_fn, hook_input):
    """Run a handler and capture its stdout JSON output."""
    with patch("sys.stdout") as mock_stdout, pytest.raises(SystemExit):
        captured = []
        mock_stdout.write = lambda s: captured.append(s)
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
        with patch(
            "cline_hooks.handlers.task_lifecycle.git.Repo", return_value=mock_repo
        ):
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


class TestHandleTaskStart:
    def _run(self, hook: HookInputTaskStart) -> dict[str, object]:
        output: list[str] = []
        with (
            patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
            pytest.raises(SystemExit),
        ):
            handle_task_start(hook)
        return cast(dict[str, object], json.loads(output[0]))

    def test_includes_memory_reminder(self, tmp_path: Path) -> None:
        with patch(
            "cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None
        ):
            result = self._run(_task_start([str(tmp_path)]))
        assert "memory" in cast(str, result["contextModification"]).lower()

    def test_git_context_included_when_present(self, tmp_path: Path) -> None:
        with patch(
            "cline_hooks.handlers.task_lifecycle.get_git_context",
            return_value="Branch: main",
        ):
            result = self._run(_task_start([str(tmp_path)]))
        assert "Branch: main" in cast(str, result["contextModification"])

    def test_cancel_is_false(self, tmp_path: Path) -> None:
        with patch(
            "cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None
        ):
            result = self._run(_task_start([str(tmp_path)]))
        assert result["cancel"] is False


class TestHandleTaskResume:
    def _run(
        self, hook: HookInputTaskResume, store: TaskStateStore | None = None
    ) -> dict[str, object]:
        output: list[str] = []
        with patch("builtins.print", side_effect=lambda s, **kw: output.append(s)):
            with patch(
                "cline_hooks.handlers.task_lifecycle._store",
                store or TaskStateStore(Path("/nonexistent")),
            ):
                with pytest.raises(SystemExit):
                    handle_task_resume(hook)
        return cast(dict[str, object], json.loads(output[0]))

    def test_includes_memory_reminder(self, tmp_path: Path) -> None:
        with patch(
            "cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None
        ):
            result = self._run(_task_resume([str(tmp_path)]))
        assert "memory" in cast(str, result["contextModification"]).lower()

    def test_block_history_included_when_present(self, tmp_path: Path) -> None:
        store = TaskStateStore(tmp_path / "state.json")
        store.record_block("task-1", "tool", "reason")
        with patch(
            "cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None
        ):
            result = self._run(_task_resume([str(tmp_path)]), store=store)
        assert "interrupted" in cast(str, result["contextModification"])

    def test_no_block_history_when_none(self, tmp_path: Path) -> None:
        with patch(
            "cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None
        ):
            result = self._run(_task_resume([str(tmp_path)]))
        assert "interrupted" not in cast(str, result["contextModification"])

    def test_skills_preserved_on_resume(self, tmp_path: Path) -> None:
        record_skill("task-1", "git-usage")
        with patch(
            "cline_hooks.handlers.task_lifecycle.get_git_context", return_value=None
        ):
            self._run(_task_resume([str(tmp_path)]))
        assert is_skill_called("task-1", "git-usage")


class TestHandleTaskCancel:
    def _run(
        self, hook: HookInputTaskCancel, store: TaskStateStore | None = None
    ) -> dict[str, object]:
        output: list[str] = []
        with patch("builtins.print", side_effect=lambda s, **kw: output.append(s)):
            with patch(
                "cline_hooks.handlers.task_lifecycle._store",
                store or TaskStateStore(Path("/nonexistent")),
            ):
                with pytest.raises(SystemExit):
                    handle_task_cancel(hook)
        return cast(dict[str, object], json.loads(output[0]))

    def test_dirty_files_warning_shown(self, tmp_path: Path) -> None:
        mock_repo = MagicMock()
        mock_repo.index.diff.return_value = [1]
        mock_repo.untracked_files = []
        with patch(
            "cline_hooks.handlers.task_lifecycle.git.Repo", return_value=mock_repo
        ):
            result = self._run(_task_cancel([str(tmp_path)]))
        assert "uncommitted" in cast(str, result["contextModification"])

    def test_no_dirty_warning_when_clean(self, tmp_path: Path) -> None:
        mock_repo = MagicMock()
        mock_repo.index.diff.return_value = []
        mock_repo.untracked_files = []
        with patch(
            "cline_hooks.handlers.task_lifecycle.git.Repo", return_value=mock_repo
        ):
            result = self._run(_task_cancel([str(tmp_path)]))
        assert "uncommitted" not in cast(str, result["contextModification"])

    def test_includes_memory_reminder(self, tmp_path: Path) -> None:
        import git.exc

        with patch(
            "cline_hooks.handlers.task_lifecycle.git.Repo",
            side_effect=git.exc.InvalidGitRepositoryError,
        ):
            result = self._run(_task_cancel([str(tmp_path)]))
        assert "memory" in cast(str, result["contextModification"]).lower()


class TestHandleTaskComplete:
    def _run(
        self, hook: HookInputTaskComplete, store: TaskStateStore | None = None
    ) -> dict[str, object]:
        output: list[str] = []
        with patch("builtins.print", side_effect=lambda s, **kw: output.append(s)):
            with patch(
                "cline_hooks.handlers.task_lifecycle._store",
                store or TaskStateStore(Path("/nonexistent")),
            ):
                with pytest.raises(SystemExit):
                    handle_task_complete(hook)
        return cast(dict[str, object], json.loads(output[0]))

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
