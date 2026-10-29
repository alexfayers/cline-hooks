from __future__ import annotations

import os
from pathlib import Path
import re
from typing import TYPE_CHECKING, cast

import git
import git.exc

from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.vocabulary import PluginScope
from cline_hooks.handlers.commands import extract_commands
from cline_hooks.handlers.search_scope import effective_cwd

if TYPE_CHECKING:
    import logging

OPT_OUT = "# new-feature"
_FOLDING_FLAGS = ("--fixup", "--squash", "--amend")
_COMMIT_ALL = re.compile(r"--all|-[a-z]*a[a-z]*")
_BASES = ("@{u}", "origin/main")
_IN_PROGRESS = ("rebase-merge", "rebase-apply", "MERGE_HEAD", "CHERRY_PICK_HEAD")
_COMMIT_MARK = "\x01"


def _repo_state(directory: str, include_unstaged: bool) -> tuple[list[list[str]], set[str]]:
    """Return the unpushed commits as [<sha> <subject>, *files] and the files the next commit changes.

    The commits are empty where there is no repo, upstream or origin/main, or a rebase, merge or cherry-pick runs.
    """
    try:
        repo = git.Repo(directory, search_parent_directories=True)
    except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
        return [], set()
    base = next((ref for ref in _BASES if repo.git.rev_parse("--verify", "--quiet", ref, with_exceptions=False)), None)
    if base is None or any((Path(repo.git_dir) / marker).exists() for marker in _IN_PROGRESS):
        return [], set()
    changed = set(repo.git.diff("HEAD" if include_unstaged else "--cached", "--name-only").splitlines())
    log = repo.git.log(f"{base}..HEAD", "--name-only", f"--format={_COMMIT_MARK}%h %s")
    return [list(filter(None, commit.splitlines())) for commit in log.split(_COMMIT_MARK)[1:]], changed


def _overlaps(directory: str, include_unstaged: bool) -> list[str]:
    """Return "<sha> <subject> (<files>)" per unpushed commit touching a file the next commit changes."""
    commits, changed = _repo_state(directory, include_unstaged)
    return [f"{title} ({', '.join(sorted(hit))})" for title, *files in commits if (hit := changed & set(files))]


def _pre_shell_guard(logger: logging.Logger, **kwargs: object) -> HookResult | None:
    """Return a block for a `git commit` whose changes overlap an unpushed commit."""
    command = cast("str", kwargs.get("command") or "")
    workspace_roots = cast("list[str]", kwargs.get("workspace_roots") or [])
    if "commit" not in command or OPT_OUT in command:
        return None

    import bashlex.errors  # ruff: ignore[import-outside-top-level]

    try:
        commands = extract_commands(bashlex.parse(command))
    except bashlex.errors.ParsingError:
        return None
    session_cwd = workspace_roots[0] if workspace_roots else os.getcwd()  # ruff: ignore[os-getcwd]
    adds = any(cmd.name == "git" and "add" in cmd.args for cmd in commands)
    for index, cmd in enumerate(commands):
        if cmd.name != "git" or "commit" not in cmd.args or any(w.startswith(_FOLDING_FLAGS) for w in cmd.words):
            continue
        directory = effective_cwd(commands, index, session_cwd)
        if "-C" in cmd.words:
            directory = os.path.join(directory, cmd.words[cmd.words.index("-C") + 1])  # ruff: ignore[os-path-join]
        if overlaps := _overlaps(directory, adds or any(_COMMIT_ALL.fullmatch(w) for w in cmd.words)):
            logger.debug("Blocked git commit: overlaps unpushed commit(s)")
            return HookResult(
                block=(
                    f"This commit overlaps unpushed commit(s): {'; '.join(overlaps)}. MUST fold it in with "
                    f"`git commit --fixup=<sha>`, or add `{OPT_OUT}` to the command if it is a separate change."
                )
            )
    return None


class FixupGuardPlugin(HooksPlugin):
    """Bundled plugin blocking new commits that overlap unpushed ones."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Return the fixup guard's block for a PreShell event, else None."""
        if hook_name == PluginScope.PRE_SHELL:
            return _pre_shell_guard(logger, **kwargs)
        return None
