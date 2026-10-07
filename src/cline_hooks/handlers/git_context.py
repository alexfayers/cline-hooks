from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("hooks.git_context")


def get_git_context(workspace_roots: list[str]) -> str | None:
    """Build a context string with git state for the first valid repo found.

    Args:
        workspace_roots: List of workspace root paths to search.

    Returns:
        Formatted string with branch, dirty file count, recent commits, and
        TODO.md status; or None if no valid git repo found.
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

        commits = [str(c.summary) for c in repo.iter_commits(max_count=3)]
        commits_str = "\n".join(f"  - {s}" for s in commits)

        todo_exists = (Path(repo.working_dir) / "TODO.md").exists()

        lines = [
            f"Branch: {branch}",
            f"Dirty files: {dirty_count}",
            f"Recent commits:\n{commits_str}",
            f"TODO.md present: {todo_exists}",
        ]
        return "\n".join(lines)

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
