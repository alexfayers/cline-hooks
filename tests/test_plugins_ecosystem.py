from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from cline_hooks.core.models import (
    HookInputPostToolUse,
    HookInputTaskResume,
    HookInputTaskStart,
    TaskStartFields,
)
from cline_hooks.core.plugin import HookResult, HooksPlugin, hookimpl
from cline_hooks.core.protocol import RawPayload, get_protocol
from cline_hooks.core.response import render
from cline_hooks.core.vocabulary import CanonicalHook
from cline_hooks.frontends.cline import ClineProtocol
from cline_hooks.handlers.post_tool_use import handle_post_tool_use
from cline_hooks.handlers.task_lifecycle import handle_task_resume, handle_task_start
from cline_hooks.plugins.ecosystem import EcosystemPlugin, ToolingNote
from cline_hooks.state.workspace import record_workspace

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from cline_hooks.core.outcome import Outcome

_UV_NOTE = "This is a Python project (pyproject.toml). SHOULD use `uv run`/`uv add`, not pip/python directly."
_NO_UV_NOTE = "This is a Python project (pyproject.toml)."
_WORKING_DIRECTORY_CHANGED = "Working directory changed"


class _ReplacingContributor(HooksPlugin):
    @hookimpl
    def ecosystem_tooling_note(self, workspace_roots: list[str]) -> ToolingNote | None:
        return ToolingNote(note="REPLACING NOTE", replaces_generic=True)


class _AdditiveContributor(HooksPlugin):
    @hookimpl
    def ecosystem_tooling_note(self, workspace_roots: list[str]) -> ToolingNote | None:
        return ToolingNote(note="ADDITIVE NOTE", replaces_generic=False)


class _PostToolUseNotePlugin(HooksPlugin):
    def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
        return HookResult(notes=["OTHER NOTE"]) if hook_name == CanonicalHook.POST_TOOL_USE else None


def _python_project(tmp_path: Path) -> list[str]:
    (tmp_path / "pyproject.toml").write_text("")
    return [str(tmp_path)]


def _context(outcome: Outcome | None) -> str:
    assert outcome is not None
    stdout = render(outcome, get_protocol()).stdout
    return cast("str", json.loads(stdout).get("contextModification", "")) if stdout else ""


def _run_task_start(roots: list[str]) -> str:
    hook = HookInputTaskStart(
        taskId="task-1", workspaceRoots=roots, hookName="TaskStart", taskStart=TaskStartFields(source="")
    )
    return _context(handle_task_start(hook))


def _run_task_resume(roots: list[str]) -> str:
    hook = HookInputTaskResume(taskId="task-1", workspaceRoots=roots, hookName="TaskResume")
    return _context(handle_task_resume(hook))


def _run_post_tool_use(roots: list[str]) -> str:
    payload = {
        "clineVersion": "1.0",
        "timestamp": "2024-01-01T00:00:00Z",
        "taskId": "task-1",
        "userId": "user-1",
        "workspaceRoots": roots,
        "hookName": "PostToolUse",
        "postToolUse": {
            "toolName": "Read",
            "parameters": {"file_path": "/x.py"},
            "success": True,
            "executionTimeMs": 10,
            "result": None,
        },
    }
    hook = ClineProtocol().parse(RawPayload.from_stdin(json.dumps(payload)))
    assert isinstance(hook, HookInputPostToolUse)
    return _context(handle_post_tool_use(hook))


class TestTaskStartToolingNote:
    def test_python_project_with_uv_gets_uv_note(self, use_plugins: Callable[..., None], tmp_path: Path) -> None:
        use_plugins(EcosystemPlugin())
        with patch("shutil.which", return_value="/usr/bin/uv"):
            context = _run_task_start(_python_project(tmp_path))
        assert _UV_NOTE in context

    def test_replacing_contributor_note_displaces_generic_note(
        self, use_plugins: Callable[..., None], tmp_path: Path
    ) -> None:
        use_plugins(EcosystemPlugin(), _ReplacingContributor())
        with patch("shutil.which", return_value="/usr/bin/uv"):
            context = _run_task_start(_python_project(tmp_path))
        assert "REPLACING NOTE" in context
        assert "This is a Python project" not in context

    def test_replacing_notes_come_before_additive_notes(self, use_plugins: Callable[..., None], tmp_path: Path) -> None:
        use_plugins(EcosystemPlugin(), _ReplacingContributor(), _AdditiveContributor())
        context = _run_task_start(_python_project(tmp_path))
        assert context.index("REPLACING NOTE") < context.index("ADDITIVE NOTE")

    def test_resume_gets_the_tooling_note(self, use_plugins: Callable[..., None], tmp_path: Path) -> None:
        use_plugins(EcosystemPlugin())
        with patch("shutil.which", return_value="/usr/bin/uv"):
            context = _run_task_resume(_python_project(tmp_path))
        assert _UV_NOTE in context

    def test_roots_without_a_marker_file_get_no_note(self, use_plugins: Callable[..., None], tmp_path: Path) -> None:
        use_plugins(EcosystemPlugin())
        assert "This is a Python project" not in _run_task_start([str(tmp_path)])

    def test_the_first_matching_root_gives_the_only_generic_note(
        self, use_plugins: Callable[..., None], tmp_path: Path
    ) -> None:
        use_plugins(EcosystemPlugin())
        first, second = tmp_path / "first", tmp_path / "second"
        first.mkdir()
        second.mkdir()
        roots = [*_python_project(first), *_python_project(second)]
        with patch("shutil.which", return_value="/usr/bin/uv"):
            context = _run_task_start(roots)
        assert context.count(_UV_NOTE) == 1


class TestWorkingDirectoryChange:
    def test_changed_roots_announce_the_new_directory_with_tooling_notes(
        self, use_plugins: Callable[..., None], tmp_path: Path
    ) -> None:
        use_plugins(EcosystemPlugin())
        record_workspace("task-1", ["/old"])
        roots = _python_project(tmp_path)
        with patch("shutil.which", return_value=None):
            context = _run_post_tool_use(roots)
        assert f"{_WORKING_DIRECTORY_CHANGED} to {tmp_path}. {_NO_UV_NOTE}" in context

    def test_unchanged_roots_give_no_note(self, use_plugins: Callable[..., None], tmp_path: Path) -> None:
        use_plugins(EcosystemPlugin())
        roots = _python_project(tmp_path)
        record_workspace("task-1", roots)
        assert _WORKING_DIRECTORY_CHANGED not in _run_post_tool_use(roots)

    def test_note_is_consumed_alongside_another_plugins_note_without_a_reminder_label(
        self, use_plugins: Callable[..., None], tmp_path: Path
    ) -> None:
        use_plugins(EcosystemPlugin(), _PostToolUseNotePlugin())
        record_workspace("task-1", ["/old"])
        roots = _python_project(tmp_path)
        first = _run_post_tool_use(roots)
        assert "OTHER NOTE" in first
        assert _WORKING_DIRECTORY_CHANGED in first
        assert "REMINDER" not in first
        assert _WORKING_DIRECTORY_CHANGED not in _run_post_tool_use(roots)
