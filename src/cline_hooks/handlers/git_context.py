from __future__ import annotations

import logging
from pathlib import Path
import subprocess

logger = logging.getLogger("hooks.git_context")

MAIN_BRANCH = "main"
MAX_UNMERGED_BRANCHES = 5
GIT_TIMEOUT_SECONDS = 5


def _git(root: str, *args: str) -> str | None:
    """Run a git command in a directory.

    Args:
        root: The directory to run git in.
        *args: The git arguments.

    Returns:
        The command's stdout, or None where git fails.
    """
    try:
        result = subprocess.run(
            ["git", "-C", root, *args],  # ruff: ignore[start-process-with-partial-path]
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _is_repo_root(root: str) -> bool:
    """Return whether a directory is the top level of a git work tree."""
    return _git(root, "rev-parse", "--show-prefix") == "\n"


def _dirty_count(root: str) -> int | None:
    """Count the files with unstaged changes plus the untracked files in a repo.

    Args:
        root: The repo to inspect.

    Returns:
        The dirty file count, or None where git fails.
    """
    unstaged = _git(root, "diff", "--name-only", "-z")
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    if unstaged is None or untracked is None:
        return None
    return unstaged.count("\0") + untracked.count("\0")


def _unmerged_branches_line(root: str) -> str | None:
    """List the local branches not merged into main, capped with a count of the rest.

    Args:
        root: The repo to inspect.

    Returns:
        The summary line, or None where there is no main branch or no unmerged branch.
    """
    no_merged = f"--no-merged=refs/heads/{MAIN_BRANCH}"
    names = (_git(root, "for-each-ref", no_merged, "--format=%(refname:short)", "refs/heads") or "").splitlines()
    if len(names) > MAX_UNMERGED_BRANCHES:
        names = [*names[:MAX_UNMERGED_BRANCHES], f"+{len(names) - MAX_UNMERGED_BRANCHES} more"]
    return f"Unmerged local branches: {', '.join(names)}" if names else None


def get_git_context(workspace_roots: list[str]) -> str | None:
    """Build a context string with git state for the first valid repo found.

    Args:
        workspace_roots: List of workspace root paths to search.

    Returns:
        Formatted string with branch, dirty file count, recent commits, and
        TODO.md status, plus unmerged branches and HANDOFF.md/RULES.md where
        present; or None if no valid git repo found.
    """
    for root in workspace_roots:
        if not _is_repo_root(root):
            continue

        head_ref = _git(root, "symbolic-ref", "-q", "HEAD")
        branch = head_ref.strip().removeprefix("refs/heads/") if head_ref else "detached HEAD"

        log = _git(root, "log", "-3", "-z", "--no-show-signature", "--format=%B")
        commits = [message.split("\n", 1)[0] for message in (log or "").split("\0")[:-1]]
        commits_str = "\n".join(f"  - {s}" for s in commits)

        root_path = Path(root)
        todo_exists = (root_path / "TODO.md").exists()

        dirty_count = _dirty_count(root)
        lines = [
            f"Branch: {branch}",
            f"Dirty files: {'unknown' if dirty_count is None else dirty_count}",
            f"Recent commits:\n{commits_str}",
            f"TODO.md present: {todo_exists}",
            _unmerged_branches_line(root),
            "HANDOFF.md present: run pickup" if (root_path / "HANDOFF.md").exists() else None,
            "RULES.md present" if (root_path / "RULES.md").exists() else None,
        ]
        return "\n".join(line for line in lines if line)

    return None


def get_dirty_count(workspace_roots: list[str]) -> int | None:
    """Return the number of dirty files in the first valid git repo found.

    Args:
        workspace_roots: List of workspace root paths to search.

    Returns:
        Dirty file count, or None if no valid repo found or git fails.
    """
    return next((_dirty_count(root) for root in workspace_roots if _is_repo_root(root)), None)
