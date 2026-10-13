from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import git

logger = logging.getLogger("hooks.git_context")

MAIN_BRANCH = "main"
MAX_UNMERGED_BRANCHES = 5


def _unmerged_branches_line(repo: git.Repo) -> str | None:
    """List the local branches not merged into main, capped with a count of the rest.

    Args:
        repo: The repo to inspect.

    Returns:
        The summary line, or None where there is no main branch or no unmerged branch.
    """
    if MAIN_BRANCH not in {head.name for head in repo.heads}:
        return None
    names = repo.git.for_each_ref(f"--no-merged={MAIN_BRANCH}", "--format=%(refname:short)", "refs/heads").splitlines()
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
    import git
    import git.exc

    for root in workspace_roots:
        try:
            repo = git.Repo(root)
        except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
            continue

        try:
            branch = repo.active_branch.name
        except TypeError:
            branch = "detached HEAD"

        dirty_count = len(repo.index.diff(None)) + len(repo.untracked_files)

        commits = [str(c.summary) for c in repo.iter_commits(max_count=3)] if repo.head.is_valid() else []
        commits_str = "\n".join(f"  - {s}" for s in commits)

        root_path = Path(repo.working_dir)
        todo_exists = (root_path / "TODO.md").exists()

        lines = [
            f"Branch: {branch}",
            f"Dirty files: {dirty_count}",
            f"Recent commits:\n{commits_str}",
            f"TODO.md present: {todo_exists}",
            _unmerged_branches_line(repo),
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
        Dirty file count, or None if no valid repo found.
    """
    import git
    import git.exc

    for root in workspace_roots:
        try:
            repo = git.Repo(root)
            return len(repo.index.diff(None)) + len(repo.untracked_files)
        except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
            continue
    return None
