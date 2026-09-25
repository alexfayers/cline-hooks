from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock, patch

import pytest

from cline_hooks.core.models import (
    HookInputTaskCancel,
    HookInputTaskComplete,
    HookInputTaskResume,
    HookInputTaskStart,
    TaskStartFields,
)
from cline_hooks.core.plugin import HookResult, HooksPlugin, ToolingNote, UserFacingNote
from cline_hooks.core.protocol import get_protocol, set_protocol
from cline_hooks.core.response import render
from cline_hooks.frontends.claude_code import ClaudeCodeProtocol
from cline_hooks.frontends.cline import ClineProtocol
from cline_hooks.frontends.kiro import KiroProtocol
from cline_hooks.handlers.git_context import (
    get_dirty_count,
    get_generic_tooling_note,
    resolve_tooling_notes,
)
from cline_hooks.handlers.task_lifecycle import (
    _format_block_history,
    _repair_claude_code_install,
    handle_task_cancel,
    handle_task_complete,
    handle_task_resume,
    handle_task_start,
)
from cline_hooks.plugins.context_usage import should_nudge_context
from cline_hooks.plugins.nudges import increment
from cline_hooks.plugins.plan_handoff import consume_plan_nudge, record_plan_exit
from cline_hooks.state.agents import has_agent_use, record_agent_use
from cline_hooks.state.memory import has_memory_writes, record_memory_write
from cline_hooks.state.skills import is_skill_called, record_skill
from cline_hooks.state.store import TaskBlockEvent, TaskStateStore
from cline_hooks.state.workspace import record_workspace, should_note_workspace_change

if TYPE_CHECKING:
    from collections.abc import Iterator

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
        with patch("git.Repo", return_value=mock_repo):
            assert get_dirty_count([str(tmp_path)]) == 3

    def test_returns_none_for_invalid_repo(self, tmp_path: Path) -> None:
        import git.exc

        with patch(
            "git.Repo",
            side_effect=git.exc.InvalidGitRepositoryError,
        ):
            assert get_dirty_count([str(tmp_path)]) is None

    def test_returns_none_for_empty_roots(self) -> None:
        assert get_dirty_count([]) is None


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


class _UserNotePlugin(HooksPlugin):
    def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
        if hook_name == "TaskStart":
            return HookResult(user_notes=[UserFacingNote(user_text="USER TEXT")])
        return None


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
    @pytest.fixture(autouse=True)
    def _no_daemon_side_effects(self) -> Iterator[None]:
        """Keep the daemon-lifecycle wiring out of every unrelated SessionStart test.

        Covered directly by TestSessionStartDaemonWiring and TestRepairClaudeCodeInstall.
        """
        with (
            patch("cline_hooks.handlers.task_lifecycle._repair_claude_code_install"),
            patch("cline_hooks.handlers.task_lifecycle.daemon_lifecycle.ensure"),
        ):
            yield

    def _run(self, hook: HookInputTaskStart) -> dict[str, object]:
        outcome = handle_task_start(hook)
        assert outcome is not None
        response = render(outcome, get_protocol())
        return cast("dict[str, object]", json.loads(response.stdout))

    def test_git_context_included_when_present(self, tmp_path: Path) -> None:
        with patch(
            "cline_hooks.plugins.session_context.get_git_context",
            return_value="Branch: main",
        ):
            result = self._run(_task_start([str(tmp_path)]))
        assert "Branch: main" in cast("str", result["contextModification"])

    def test_cancel_is_false(self, tmp_path: Path) -> None:
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            result = self._run(_task_start([str(tmp_path)]))
        assert result["cancel"] is False

    def test_agent_use_reset_on_start(self, tmp_path: Path) -> None:
        record_agent_use("task-1", "Agent")
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)]))
        assert not has_agent_use("task-1")

    def test_context_band_reset_on_start(self, tmp_path: Path) -> None:
        should_nudge_context("task-1", 210_000)
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)]))
        assert should_nudge_context("task-1", 210_000) is True

    def test_plan_exit_reset_on_start(self, tmp_path: Path) -> None:
        record_plan_exit("task-1")
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)]))
        assert consume_plan_nudge("task-1") is False

    def test_skill_preserved_on_compact(self, tmp_path: Path) -> None:
        record_skill("task-1", "git-usage")
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)], source="compact"))
        assert is_skill_called("task-1", "git-usage")

    def test_memory_writes_preserved_on_compact(self, tmp_path: Path) -> None:
        record_memory_write("task-1", "create_entities")
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)], source="compact"))
        assert has_memory_writes("task-1")

    def test_agent_use_preserved_on_compact(self, tmp_path: Path) -> None:
        record_agent_use("task-1", "Agent")
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)], source="compact"))
        assert has_agent_use("task-1")

    def test_context_band_preserved_on_compact(self, tmp_path: Path) -> None:
        should_nudge_context("task-1", 210_000)
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)], source="compact"))
        assert should_nudge_context("task-1", 210_000) is False

    def test_turns_preserved_on_compact(self, tmp_path: Path) -> None:
        increment("task-1")
        increment("task-1")
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)], source="compact"))
        assert increment("task-1") == 3

    def test_skill_preserved_on_resume(self, tmp_path: Path) -> None:
        record_skill("task-1", "git-usage")
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)], source="resume"))
        assert is_skill_called("task-1", "git-usage")

    def test_skill_reset_on_startup(self, tmp_path: Path) -> None:
        record_skill("task-1", "git-usage")
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            self._run(_task_start([str(tmp_path)], source="startup"))
        assert not is_skill_called("task-1", "git-usage")

    def test_git_context_emitted_on_compact(self, tmp_path: Path) -> None:
        with patch(
            "cline_hooks.plugins.session_context.get_git_context",
            return_value="Branch: main",
        ):
            result = self._run(_task_start([str(tmp_path)], source="compact"))
        assert "Branch: main" in cast("str", result["contextModification"])

    def test_tooling_note_included_when_unreplaced(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.plugins.session_context.get_git_context", return_value=None),
            patch(
                "cline_hooks.handlers.task_lifecycle.load_plugins",
                return_value=[HooksPlugin()],
            ),
            patch(
                "cline_hooks.handlers.git_context.get_generic_tooling_note",
                return_value="TOOLING NOTE",
            ),
        ):
            result = self._run(_task_start([str(tmp_path)]))
        assert "TOOLING NOTE" in cast("str", result["contextModification"])

    def test_tooling_note_replaced_when_plugin_replaces(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.plugins.session_context.get_git_context", return_value=None),
            patch(
                "cline_hooks.handlers.task_lifecycle.load_plugins",
                return_value=[_ReplacingPlugin()],
            ),
            patch(
                "cline_hooks.handlers.git_context.get_generic_tooling_note",
                return_value="TOOLING NOTE",
            ),
        ):
            result = self._run(_task_start([str(tmp_path)]))
        assert "TOOLING NOTE" not in cast("str", result["contextModification"])

    def test_workspace_state_seeded_on_start(self, tmp_path: Path) -> None:
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
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
            patch("cline_hooks.plugins.session_context.get_git_context", return_value=None),
            patch(
                "cline_hooks.handlers.task_lifecycle.load_plugins",
                return_value=[_CapturingPlugin()],
            ),
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
            patch("cline_hooks.plugins.session_context.get_git_context", return_value=None),
            patch(
                "cline_hooks.handlers.task_lifecycle.load_plugins",
                return_value=[_CapturingPlugin()],
            ),
        ):
            self._run(_task_start([str(tmp_path)], agent_type="Explore"))
        assert captured.get("agent_type") == "Explore"

    def _run_raw(self, hook: HookInputTaskStart) -> str:
        outcome = handle_task_start(hook)
        assert outcome is not None
        return render(outcome, get_protocol()).stdout

    def test_user_note_goes_to_system_message_on_claude_code(self, tmp_path: Path) -> None:
        set_protocol(ClaudeCodeProtocol("SessionStart"))
        try:
            with (
                patch(
                    "cline_hooks.plugins.session_context.get_git_context",
                    return_value=None,
                ),
                patch(
                    "cline_hooks.handlers.task_lifecycle.load_plugins",
                    return_value=[_UserNotePlugin()],
                ),
            ):
                raw = self._run_raw(_task_start([str(tmp_path)]))
        finally:
            set_protocol(ClineProtocol())
        payload = json.loads(raw)
        assert payload["systemMessage"] == "USER TEXT"

    def test_user_note_not_shown_to_model_without_user_channel(self, tmp_path: Path) -> None:
        set_protocol(KiroProtocol())
        try:
            with (
                patch(
                    "cline_hooks.plugins.session_context.get_git_context",
                    return_value=None,
                ),
                patch(
                    "cline_hooks.handlers.task_lifecycle.load_plugins",
                    return_value=[_UserNotePlugin()],
                ),
            ):
                raw = self._run_raw(_task_start([str(tmp_path)]))
        finally:
            set_protocol(ClineProtocol())
        assert "USER TEXT" not in raw
        assert "systemMessage" not in raw


class TestSessionStartDaemonWiring:
    @pytest.fixture(autouse=True)
    def _claude_code_protocol(self) -> Iterator[None]:
        set_protocol(ClaudeCodeProtocol("SessionStart"))
        try:
            yield
        finally:
            set_protocol(ClineProtocol())

    def test_repair_and_ensure_are_both_called(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.plugins.session_context.get_git_context", return_value=None),
            patch("cline_hooks.handlers.task_lifecycle._repair_claude_code_install") as repair,
            patch("cline_hooks.handlers.task_lifecycle.daemon_lifecycle.ensure") as ensure,
        ):
            handle_task_start(_task_start([str(tmp_path)]))
        repair.assert_called_once()
        ensure.assert_called_once()

    def test_a_repair_failure_is_logged_and_swallowed(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.plugins.session_context.get_git_context", return_value=None),
            patch(
                "cline_hooks.handlers.task_lifecycle._repair_claude_code_install",
                side_effect=RuntimeError("boom"),
            ),
            patch("cline_hooks.handlers.task_lifecycle.daemon_lifecycle.ensure") as ensure,
        ):
            outcome = handle_task_start(_task_start([str(tmp_path)]))
        assert outcome is not None
        ensure.assert_called_once()

    def test_an_ensure_failure_is_logged_and_swallowed(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.plugins.session_context.get_git_context", return_value=None),
            patch("cline_hooks.handlers.task_lifecycle._repair_claude_code_install") as repair,
            patch(
                "cline_hooks.handlers.task_lifecycle.daemon_lifecycle.ensure",
                side_effect=RuntimeError("boom"),
            ),
        ):
            outcome = handle_task_start(_task_start([str(tmp_path)]))
        assert outcome is not None
        repair.assert_called_once()


class TestRepairClaudeCodeInstall:
    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
        monkeypatch.delenv("CLINE_HOOKS_DAEMON_PORT", raising=False)
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch("cline_hooks.core.install.sys.executable", str(tmp_path / "bin" / "python")),
            patch("cline_hooks.core.daemon_config._DAEMON_CONFIG_PATH", tmp_path / "daemon.json"),
            patch("cline_hooks.frontends.claude_code.install.post_retire"),
            patch("cline_hooks.handlers.task_lifecycle._INSTALL_STAMP_PATH", tmp_path / "install-check.json"),
            patch("cline_hooks.handlers.task_lifecycle.package_version", return_value="1.2.3"),
        ):
            yield

    def _settings_path(self, tmp_path: Path) -> Path:
        return tmp_path / ".claude" / "settings.json"

    def test_installs_claude_code_hooks_when_settings_json_is_missing(self, tmp_path: Path) -> None:
        _repair_claude_code_install()
        settings = json.loads(self._settings_path(tmp_path).read_text())
        assert "PostToolUse" in settings["hooks"]

    def test_writes_a_version_stamped_hash_after_checking(self, tmp_path: Path) -> None:
        _repair_claude_code_install()
        stamp = json.loads((tmp_path / "install-check.json").read_text())
        assert stamp["version"] == "1.2.3"
        assert stamp["hash"]

    def test_second_call_at_the_same_version_skips_the_settings_json_check(self) -> None:
        _repair_claude_code_install()
        with patch("cline_hooks.handlers.task_lifecycle._claude_code_hooks_drifted") as drifted:
            _repair_claude_code_install()
        drifted.assert_not_called()

    def test_a_version_bump_re_runs_the_check(self) -> None:
        _repair_claude_code_install()
        with (
            patch("cline_hooks.handlers.task_lifecycle.package_version", return_value="9.9.9"),
            patch(
                "cline_hooks.handlers.task_lifecycle._claude_code_hooks_drifted",
                return_value=False,
            ) as drifted,
        ):
            _repair_claude_code_install()
        drifted.assert_called_once()

    def test_reinstalls_when_an_entry_is_missing_while_preserving_other_keys(self, tmp_path: Path) -> None:
        settings_path = self._settings_path(tmp_path)
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(json.dumps({"other": "value"}))
        _repair_claude_code_install()
        settings = json.loads(settings_path.read_text())
        assert settings["other"] == "value"
        assert "PostToolUse" in settings["hooks"]

    def test_leaves_an_already_correct_install_unrewritten(self, tmp_path: Path) -> None:
        _repair_claude_code_install()
        settings_path = self._settings_path(tmp_path)
        before = settings_path.read_text()
        (tmp_path / "install-check.json").unlink()
        _repair_claude_code_install()
        assert settings_path.read_text() == before


class TestHandleTaskResume:
    def _run(self, hook: HookInputTaskResume, store: TaskStateStore | None = None) -> dict[str, object]:
        with patch(
            "cline_hooks.handlers.task_lifecycle._store",
            store or TaskStateStore(Path("/nonexistent")),
        ):
            outcome = handle_task_resume(hook)
        assert outcome is not None
        response = render(outcome, get_protocol())
        return cast("dict[str, object]", json.loads(response.stdout))

    def test_block_history_included_when_present(self, tmp_path: Path) -> None:
        store = TaskStateStore(tmp_path / "state.json")
        store.record_block("task-1", "tool", "reason")
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            result = self._run(_task_resume([str(tmp_path)]), store=store)
        assert "interrupted" in cast("str", result["contextModification"])

    def test_no_block_history_when_none(self, tmp_path: Path) -> None:
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            result = self._run(_task_resume([str(tmp_path)]))
        assert "interrupted" not in cast("str", result.get("contextModification", ""))

    def test_skills_preserved_on_resume(self, tmp_path: Path) -> None:
        record_skill("task-1", "git-usage")
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            self._run(_task_resume([str(tmp_path)]))
        assert is_skill_called("task-1", "git-usage")

    def test_agent_use_preserved_on_resume(self, tmp_path: Path) -> None:
        record_agent_use("task-1", "Agent")
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            self._run(_task_resume([str(tmp_path)]))
        assert has_agent_use("task-1")

    def test_tooling_note_included_when_unreplaced(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.plugins.session_context.get_git_context", return_value=None),
            patch(
                "cline_hooks.handlers.task_lifecycle.load_plugins",
                return_value=[HooksPlugin()],
            ),
            patch(
                "cline_hooks.handlers.git_context.get_generic_tooling_note",
                return_value="TOOLING NOTE",
            ),
        ):
            result = self._run(_task_resume([str(tmp_path)]))
        assert "TOOLING NOTE" in cast("str", result["contextModification"])

    def test_tooling_note_replaced_when_plugin_replaces(self, tmp_path: Path) -> None:
        with (
            patch("cline_hooks.plugins.session_context.get_git_context", return_value=None),
            patch(
                "cline_hooks.handlers.task_lifecycle.load_plugins",
                return_value=[_ReplacingPlugin()],
            ),
            patch(
                "cline_hooks.handlers.git_context.get_generic_tooling_note",
                return_value="TOOLING NOTE",
            ),
        ):
            result = self._run(_task_resume([str(tmp_path)]))
        assert "TOOLING NOTE" not in cast("str", result["contextModification"])

    def test_workspace_state_seeded_on_resume(self, tmp_path: Path) -> None:
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            self._run(_task_resume([str(tmp_path)]))
        assert should_note_workspace_change("task-1", [str(tmp_path)]) is False
        assert should_note_workspace_change("task-1", ["/other"]) is True

    def test_block_reason_naming_skill_re_nudges_that_skill(self, tmp_path: Path) -> None:
        store = TaskStateStore(tmp_path / "state.json")
        store.record_block(
            "task-1",
            "execute_command",
            "MUST use the `git-usage` skill before running this command",
        )
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            result = self._run(_task_resume([str(tmp_path)]), store=store)
        context = cast("str", result["contextModification"])
        assert "REQUIRED" in context
        assert "`git-usage`" in context

    def test_block_reason_without_skill_mention_is_not_re_nudged(self, tmp_path: Path) -> None:
        store = TaskStateStore(tmp_path / "state.json")
        store.record_block("task-1", "execute_command", "some unrelated block reason")
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            result = self._run(_task_resume([str(tmp_path)]), store=store)
        assert "REQUIRED" not in cast("str", result["contextModification"])

    def test_multiple_distinct_skills_are_listed_sorted_and_deduplicated(self, tmp_path: Path) -> None:
        store = TaskStateStore(tmp_path / "state.json")
        store.record_block(
            "task-1",
            "execute_command",
            "MUST use the `cr` skill before running this command",
        )
        store.record_block(
            "task-1",
            "execute_command",
            "MUST use the `git-usage` skill before running this command",
        )
        store.record_block(
            "task-1",
            "execute_command",
            "MUST use the `cr` skill before running this command",
        )
        with patch("cline_hooks.plugins.session_context.get_git_context", return_value=None):
            result = self._run(_task_resume([str(tmp_path)]), store=store)
        context = cast("str", result["contextModification"])
        assert "`cr`, `git-usage`" in context


class TestHandleTaskCancel:
    def _run(self, hook: HookInputTaskCancel, store: TaskStateStore | None = None) -> dict[str, object]:
        with patch(
            "cline_hooks.handlers.task_lifecycle._store",
            store or TaskStateStore(Path("/nonexistent")),
        ):
            outcome = handle_task_cancel(hook)
        assert outcome is not None
        response = render(outcome, get_protocol())
        return cast("dict[str, object]", json.loads(response.stdout))

    def test_no_output_when_no_blocks(self, tmp_path: Path) -> None:
        result = self._run(_task_cancel([str(tmp_path)]))
        assert cast("str", result.get("contextModification", "")) == ""


class TestHandleTaskComplete:
    def _run(self, hook: HookInputTaskComplete, store: TaskStateStore | None = None) -> dict[str, object]:
        with patch(
            "cline_hooks.handlers.task_lifecycle._store",
            store or TaskStateStore(Path("/nonexistent")),
        ):
            outcome = handle_task_complete(hook)
        assert outcome is not None
        response = render(outcome, get_protocol())
        return cast("dict[str, object]", json.loads(response.stdout))

    def test_clears_blocks_on_complete(self, tmp_path: Path) -> None:
        store = TaskStateStore(tmp_path / "state.json")
        store.record_block("task-1", "tool", "reason")
        self._run(_task_complete([str(tmp_path)]), store=store)
        assert store.get_blocks("task-1") == []

    def test_no_context_injected(self, tmp_path: Path) -> None:
        result = self._run(_task_complete([str(tmp_path)]))
        assert "contextModification" not in result

    def test_agent_use_reset_on_complete(self, tmp_path: Path) -> None:
        record_agent_use("task-1", "Agent")
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
