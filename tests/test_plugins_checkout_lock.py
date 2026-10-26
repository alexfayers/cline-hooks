from __future__ import annotations

import json
import logging
from pathlib import Path
import shlex
import time
from unittest.mock import patch

import git
import pytest

from cline_hooks._main import _run_hook, main
from cline_hooks.core.install import binary_names
from cline_hooks.core.plugin import HookResult, plugins_override
from cline_hooks.core.vocabulary import CanonicalTool
from cline_hooks.plugins.checkout_lock import LOCK_TTL_SECONDS, CheckoutLockPlugin, _git_dir_of

COMMIT = "git commit -m x"
WRITE = "echo hi > a.txt"
FRONTENDS = {
    "pi": ("tool_call", "bash", "agent_settled", "session_shutdown", {"agent_id": "x"}),
    "claude": ("PreToolUse", "Bash", "Stop", "SessionEnd", {}),
}


@pytest.fixture
def primary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    trees = [tmp_path / "primary", tmp_path / "linked"]
    for tree in trees:
        tree.mkdir()

    def git_dir_of(path: str) -> str | None:
        return next((str(tree.with_suffix(".git")) for tree in trees if Path(path).is_relative_to(tree)), None)

    monkeypatch.setattr("cline_hooks.plugins.checkout_lock._git_dir_of", git_dir_of)
    return trees[0]


def _fire(hook: str, root: Path, session: str, **kwargs: object) -> HookResult | None:
    return CheckoutLockPlugin().on_hook(
        hook, logger=logging.getLogger("test"), task_id=session, workspace_roots=[str(root)], **kwargs
    )


def _edit(root: Path, session: str, name: str) -> HookResult | None:
    return _fire("PreToolUse", root, session, tool_name=CanonicalTool.EDIT, parameters={"path": name})


def _shell(root: Path, session: str, command: str) -> HookResult | None:
    return _fire("PreShell", root, session, tool_name=CanonicalTool.SHELL, command=command)


@pytest.mark.parametrize(
    ("first", "second", "blocked"),
    [
        (WRITE, WRITE, True),
        ("sed -i s/a/b/ a.txt", WRITE, True),
        (WRITE, "echo hi > b.txt", False),
        (COMMIT, WRITE, True),
        (WRITE, COMMIT, True),
        (COMMIT, "git status", False),
        (COMMIT, "git push origin main", False),
        (COMMIT, "echo hi > TMP/loose.txt", False),
        (COMMIT, "git -C $HOME/no-such-dir-here add x", False),
        ("cd LINKED && " + COMMIT, "git -C LINKED add x", True),
        ("git -C LINKED commit -m x", COMMIT, False),
    ],
)
def test_another_session_is_blocked_only_by_a_conflicting_lock(
    primary: Path, first: str, second: str, blocked: bool
) -> None:
    linked = primary.with_name("linked")
    first, second = (c.replace("LINKED", str(linked)).replace("TMP", str(primary.parent)) for c in (first, second))
    assert _shell(primary, "s1", first) is None
    result = _shell(primary, "s2", second)
    assert bool(result and result.block) is blocked
    if blocked:
        assert "cline-hook unlock" in str(result and result.block)
        assert _shell(primary, "s1", second) is None


def test_lock_is_free_after_the_ttl(primary: Path) -> None:
    _shell(primary, "s1", COMMIT)
    with patch("cline_hooks.plugins.checkout_lock.time.time", return_value=time.time() + LOCK_TTL_SECONDS + 1):
        assert _edit(primary, "s2", "a.txt") is None


@pytest.mark.parametrize(("args", "freed", "kept"), [("unlock a.txt", "a.txt", "b.txt"), ("unlock", "b.txt", None)])
def test_unlock_drops_the_sessions_locks(
    primary: Path, monkeypatch: pytest.MonkeyPatch, args: str, freed: str, kept: str | None
) -> None:
    _edit(primary, "s1", "a.txt")
    _edit(primary, "s1", "b.txt")
    rewritten = _shell(primary, "s1", f"{binary_names()[0]} {args}")
    assert rewritten is not None
    assert rewritten.updated_input is not None
    monkeypatch.chdir(primary)
    monkeypatch.setattr("sys.argv", shlex.split(rewritten.updated_input["command"]))
    with pytest.raises(SystemExit):
        main()
    assert _edit(primary, "s2", freed) is None
    assert kept is None or _edit(primary, "s2", kept) is not None


def _hook(frontend: str, session: str, cwd: Path, event: str, command: str = "") -> int:
    pre_tool, tool, idle, end, extra = FRONTENDS[frontend]
    events: dict[str, dict[str, object]] = {
        "shell": {"hook_event_name": pre_tool, "tool_name": tool, "tool_input": {"command": command}},
        "idle": {"hook_event_name": idle},
        "end": {"hook_event_name": end},
    }
    payload = {"session_id": session, "cwd": str(cwd), **extra, **events[event]}
    with (
        plugins_override([CheckoutLockPlugin()]),
        patch("builtins.input", return_value=json.dumps(payload)),
        pytest.raises(SystemExit) as exit_info,
    ):
        _run_hook()
    return int(exit_info.value.code or 0)


@pytest.mark.parametrize("frontend", FRONTENDS)
@pytest.mark.parametrize("operation", [True, False])
def test_turn_end_frees_the_tree_lock_unless_a_git_operation_runs(
    primary: Path, frontend: str, operation: bool
) -> None:
    linked = primary.with_name("linked")
    rebase = f"cd {linked} && git rebase main"
    assert _hook(frontend, "s1", primary, "shell", rebase) == 0
    assert _hook(frontend, "s2", primary, "shell", rebase) == 2
    if operation:
        (linked.with_suffix(".git") / "rebase-merge").mkdir(parents=True)
    _hook(frontend, "s1", primary, "idle")
    assert _hook(frontend, "s2", primary, "shell", rebase) == (2 if operation else 0)
    _hook(frontend, "s1", primary, "end")
    assert _hook(frontend, "s2", primary, "shell", rebase) == 0


def test_lock_is_freed_once_the_owning_process_has_exited(primary: Path) -> None:
    assert _hook("pi", "s1", primary, "shell", COMMIT) == 0
    assert _hook("pi", "s2", primary, "shell", COMMIT) == 2
    with patch("cline_hooks.plugins.checkout_lock.os.kill", side_effect=ProcessLookupError):
        assert _hook("pi", "s2", primary, "shell", COMMIT) == 0


def test_git_dir_of_gives_each_worktree_its_own_git_directory(tmp_path: Path) -> None:
    main_repo = git.Repo.init(tmp_path / "main", initial_branch="main")
    with main_repo.config_writer() as config:
        config.set_value("user", "name", "Test").set_value("user", "email", "test@example.com")
    main_repo.index.commit("initial", skip_hooks=True)
    main_repo.git.worktree("add", str(tmp_path / "other"), "-b", "feature")
    assert _git_dir_of(str(tmp_path / "main" / "not-yet" / "new.txt")) == str(main_repo.git_dir)
    assert _git_dir_of(str(tmp_path / "other")) not in {None, str(main_repo.git_dir)}
    assert _git_dir_of(str(tmp_path / "loose.txt")) is None
