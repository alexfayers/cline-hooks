from __future__ import annotations

from pathlib import Path

import git
import git.exc

from cline_hooks.config import get_push_block_markers


def marker_above_repo(workspace_roots: list[str]) -> str | None:
    """Return the first configured marker found at or above the repo root, else None.

    Returns:
        The matching marker name, or None if no markers are configured, no repo is
        found in workspace_roots, or no marker matches any ancestor of the repo root
        (inclusive of the repo root itself).
    """
    markers = get_push_block_markers()
    if not markers:
        return None

    for root in workspace_roots:
        try:
            repo = git.Repo(root, search_parent_directories=True)
        except (git.exc.InvalidGitRepositoryError, git.exc.NoSuchPathError):
            continue

        current = Path(repo.working_dir)
        while True:
            for marker in markers:
                if (current / marker).exists():
                    return marker
            if current == current.parent:
                break
            current = current.parent

    return None
