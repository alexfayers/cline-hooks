from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import git
import pytest

from cline_hooks._main import _run_hook
from cline_hooks.core.plugin import HooksPlugin, load_plugins, plugins_override
from cline_hooks.plugins.agent_worktree import AgentWorktreePlugin
from cline_hooks.plugins.tool_guards import ToolGuardsPlugin

if TYPE_CHECKING:
    from pathlib import Path

PI_EDIT = {"hook_event_name": "tool_call", "tool_name": "edit", "agent_type": "writer", "agent_id": "x"}
EDITS = [{"oldText": "a", "newText": "b"}]


@pytest.fixture
def trees(tmp_path: Path) -> tuple[Path, Path]:
    primary = tmp_path / "primary"
    repo = git.Repo.init(primary)
    repo.git.execute(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-m", "x"])
    worktree = tmp_path / "worktree"
    repo.git.worktree("add", "--detach", str(worktree))
    return primary, worktree


def _run(
    capsys: pytest.CaptureFixture[str],
    cwd: Path,
    call: dict[str, str],
    tool_input: dict[str, object],
    *plugins: HooksPlugin,
) -> dict[str, object] | None:
    payload = {"session_id": "s1", "cwd": str(cwd), **call, "tool_input": tool_input}
    with (
        plugins_override([AgentWorktreePlugin(), *plugins]),
        patch("sys.stdin", io.StringIO(json.dumps(payload))),
        pytest.raises(SystemExit),
    ):
        _run_hook()
    output = capsys.readouterr().out
    return json.loads(output) if output else None


def test_writer_edit_in_the_primary_checkout_runs_on_the_same_file_in_its_worktree(
    capsys: pytest.CaptureFixture[str], trees: tuple[Path, Path]
) -> None:
    primary, worktree = trees
    output = _run(capsys, worktree, PI_EDIT, {"path": str(primary / "src" / "a.py"), "edits": EDITS})
    assert output is not None
    assert output["updated_input"] == {"path": str(worktree / "src" / "a.py"), "edits": EDITS}


def test_the_comment_guard_still_sees_a_redirected_edit(
    capsys: pytest.CaptureFixture[str], trees: tuple[Path, Path]
) -> None:
    primary, worktree = trees
    edits = [{"oldText": "a", "newText": "# this comment explains why the change was made\nb"}]
    tool_input: dict[str, object] = {"path": str(primary / "a.py"), "edits": edits}
    output = _run(capsys, worktree, PI_EDIT, tool_input, ToolGuardsPlugin())
    assert output is not None
    assert output["updated_input"] == {"path": str(worktree / "a.py"), "edits": edits}
    assert "MUST NOT add a comment" in str(output["message"])


def test_relative_path_is_taken_from_the_worktree_and_left_alone(
    capsys: pytest.CaptureFixture[str], trees: tuple[Path, Path]
) -> None:
    _, worktree = trees
    assert _run(capsys, worktree, PI_EDIT, {"path": "src/a.py", "edits": EDITS}) is None


@pytest.mark.parametrize(
    ("call", "location"),
    [
        (PI_EDIT, "worktree"),
        (PI_EDIT, "elsewhere"),
        ({**PI_EDIT, "agent_type": "reader"}, "primary"),
        ({**PI_EDIT, "tool_name": "read"}, "primary"),
        ({**PI_EDIT, "tool_name": "Edit", "hook_event_name": "PreToolUse"}, "primary"),
    ],
    ids=["in-the-worktree", "outside-the-repo", "not-a-writer", "not-an-edit", "not-pi"],
)
def test_other_calls_are_unchanged(
    capsys: pytest.CaptureFixture[str], trees: tuple[Path, Path], call: dict[str, str], location: str
) -> None:
    primary, worktree = trees
    where = {"primary": primary, "worktree": worktree, "elsewhere": worktree.parent / "other"}[location]
    assert _run(capsys, worktree, call, {"path": str(where / "a.py"), "edits": EDITS}) is None


def test_the_redirect_runs_before_the_checkout_lock_so_the_lock_covers_the_worktree_file() -> None:
    names = [type(plugin).__name__ for plugin in load_plugins()]
    assert names.index("AgentWorktreePlugin") < names.index("CheckoutLockPlugin")
