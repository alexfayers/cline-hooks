from __future__ import annotations

import os
from pathlib import Path
import shlex
import time
from typing import TYPE_CHECKING, TypedDict, cast

import git

from cline_hooks.core.hook_kwargs import PreShellKwargs, PreToolUseKwargs
from cline_hooks.core.install import binary_names
from cline_hooks.core.parameters import FileEditParameters, parameters_for
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.vocabulary import FILE_EDIT_TOOLS, CanonicalHook, PluginScope
from cline_hooks.handlers.commands import ParsedCommand, extract_commands, is_read_only_git
from cline_hooks.handlers.search_scope import effective_cwd
from cline_hooks.state.jsonfile import updated_json
from cline_hooks.state.paths import get_data_dir

if TYPE_CHECKING:
    import logging

LOCK_TTL_SECONDS = 5 * 60
UNLOCK_COMMAND = "cline-hook unlock"
TREE_NEUTRAL_GIT = frozenset({"push", "fetch", "worktree", "remote", "config", "clone", "init"})
_LOCKS_PATH = get_data_dir() / "checkout-locks.json"
_TREE = ""
_OPERATION_MARKERS = ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD", "BISECT_LOG")


class _Lock(TypedDict):
    git_dir: str
    name: str  # a file's resolved path, or _TREE for the whole working tree
    session: str
    at: float
    pid: int | None


def _base(workspace_roots: list[str]) -> str:
    return workspace_roots[0] if workspace_roots else os.getcwd()  # ruff: ignore[os-getcwd]


def _resolve(path: str, base: str) -> str | None:
    """Return the absolute path, or None where a shell variable or substitution makes it unknown."""
    if any(marker in path + base for marker in "$`"):
        return None
    return str(Path(base, Path(path).expanduser()))


def _git_dir_of(path: str) -> str | None:
    """Return the git directory of the working tree holding the path, or None outside any repo."""
    absolute = Path(path).absolute()
    directory = next(candidate for candidate in (absolute, *absolute.parents) if candidate.is_dir())
    try:
        repo = git.Repo(directory, search_parent_directories=True)
    except git.InvalidGitRepositoryError:
        return None
    return None if repo.bare else str(repo.git_dir)


def _alive(lock: _Lock, now: float) -> bool:
    try:
        os.kill(lock["pid"] or os.getpid(), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return now - lock["at"] < LOCK_TTL_SECONDS


def _claim(paths: list[str | None], session: str, *, tree: bool = False) -> str | None:
    """Return a block message if another session holds a conflicting lock, else take the session's lock."""
    now = time.time()
    spec = get_protocol().frontend_spec
    pid = os.getppid() if spec is not None and spec.name in {"pi", "claude-code"} else None
    for path in paths:
        if path is None or (git_dir := _git_dir_of(path)) is None or (tree and not Path(path).is_dir()):
            continue
        name = _TREE if tree else str(Path(path).resolve())
        with updated_json(_LOCKS_PATH, list[_Lock]()) as locks:
            mine = (session, git_dir, name)
            locks[:] = [lock for lock in locks if _alive(lock, now)]
            locks[:] = [lock for lock in locks if (lock["session"], lock["git_dir"], lock["name"]) != mine]
            holder = next((lock for lock in locks if _conflicts(lock, git_dir, name, session)), None)
            if holder is None:
                locks.append({"git_dir": git_dir, "name": name, "session": session, "at": now, "pid": pid})
        if holder is not None:
            minutes_left = max(1, int((LOCK_TTL_SECONDS - (now - holder["at"])) // 60))
            return (
                f"Cannot change {path}: {holder['name'] or 'the checkout'} is locked by session {holder['session']}, "
                f"free in {minutes_left} min. MUST create your own worktree (`git worktree add <path> -b <branch>`) "
                f"and work there. Run `{UNLOCK_COMMAND} [path]` when you are done with a file."
            )
    return None


def _conflicts(lock: _Lock, git_dir: str, name: str, session: str) -> bool:
    same_name = lock["name"] == name or _TREE in {lock["name"], name}
    return lock["git_dir"] == git_dir and lock["session"] != session and same_name


def _mid_operation(lock: _Lock) -> bool:
    return lock["name"] == _TREE and any((Path(lock["git_dir"]) / marker).exists() for marker in _OPERATION_MARKERS)


def release(session: str, path: str | None = None, *, idle: bool = False) -> None:
    """Drop the session's locks, or only the one on `path`; `idle` keeps a tree lock while a git operation runs."""
    with updated_json(_LOCKS_PATH, list[_Lock]()) as locks:
        if path is None:
            locks[:] = [lock for lock in locks if lock["session"] != session or (idle and _mid_operation(lock))]
        else:
            locks[:] = [lock for lock in locks if lock["name"] != str(Path(path).resolve())]


def _git_target(words: list[str], base: str) -> tuple[str | None, str | None]:
    directory: str | None = base
    remaining = iter(words)
    for word in remaining:
        if word == "-C":
            directory = directory and _resolve(next(remaining, ""), directory)
        elif word == "-c":
            next(remaining, None)
        elif not word.startswith("-"):
            return word, directory
    return None, directory


def _written_files(command: ParsedCommand, base: str) -> list[str | None]:
    files = list(command.redirect_outputs)
    if command.name == "sed" and any(flag == "-i" or flag.startswith(("-i", "--in-place")) for flag in command.flags):
        files += command.args[1:]
    return [_resolve(file, base) for file in files]


def _pre_tool_use(kwargs: PreToolUseKwargs) -> HookResult | None:
    if kwargs.tool_name not in FILE_EDIT_TOOLS:
        return None
    path = cast("FileEditParameters", parameters_for(kwargs.tool_name, kwargs.parameters)).path
    message = path and _claim([_resolve(path, _base(kwargs.workspace_roots))], kwargs.task_id)
    return HookResult(block=message) if message else None


def _pre_shell(kwargs: PreShellKwargs) -> HookResult | None:
    import bashlex.errors  # ruff: ignore[import-outside-top-level]

    try:
        commands = extract_commands(bashlex.parse(kwargs.command))
    except bashlex.errors.ParsingError:
        return None
    for index, command in enumerate(commands):
        base = effective_cwd(commands, index, _base(kwargs.workspace_roots))
        if command.name in binary_names() and command.args[:1] == ["unlock"]:
            if "--session" in command.words:
                return None
            flagged = f"{UNLOCK_COMMAND} --session {shlex.quote(kwargs.task_id)}"
            return HookResult(
                updated_input={"command": kwargs.command.replace(UNLOCK_COMMAND, flagged, 1)},
                fallback_notes=[f"MUST run `{flagged} [path]` so the unlock names your session."],
            )
        message = _claim(_written_files(command, base), kwargs.task_id)
        if message is None and command.name == "git" and not is_read_only_git(command):
            subcommand, directory = _git_target(command.words, base)
            if subcommand is not None and subcommand not in TREE_NEUTRAL_GIT:
                message = _claim([directory], kwargs.task_id, tree=True)
        if message:
            return HookResult(block=message)
    return None


class CheckoutLockPlugin(HooksPlugin):
    """Bundled plugin giving each file and git working tree a single editing session."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Return a block for an edit or git command on another session's lock, and release locks as sessions end."""
        if hook_name == CanonicalHook.PRE_TOOL_USE:
            return _pre_tool_use(PreToolUseKwargs.build(kwargs))
        if hook_name == PluginScope.PRE_SHELL:
            return _pre_shell(PreShellKwargs.build(kwargs))
        ends_turn = hook_name == CanonicalHook.AGENT_IDLE or (
            hook_name == CanonicalHook.STOP and CanonicalHook.AGENT_IDLE not in get_protocol().supported_hooks
        )
        if ends_turn or hook_name in {CanonicalHook.SUBAGENT_STOP, CanonicalHook.SESSION_END}:
            release(str(kwargs.get("task_id") or ""), idle=ends_turn)
        return None
