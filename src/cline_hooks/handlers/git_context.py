from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import shutil
from typing import TYPE_CHECKING

import git
import git.exc

if TYPE_CHECKING:
    from cline_hooks.core.plugin import HooksPlugin

logger = logging.getLogger("hooks")


def get_git_context(workspace_roots: list[str]) -> str | None:
    """Build a context string with git state for the first valid repo found.

    Args:
        workspace_roots: List of workspace root paths to search.

    Returns:
        Formatted string with branch, dirty file count, recent commits, and
        TODO.md status; or None if no valid git repo found.
    """
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


@dataclass(frozen=True)
class ToolingDetector:
    """One ecosystem's marker file, preferred tool, and guidance notes."""

    marker_file: str
    command: str
    note_with_tool: str
    note_without_tool: str


_DETECTORS: tuple[ToolingDetector, ...] = (
    ToolingDetector(
        marker_file="pyproject.toml",
        command="uv",
        note_with_tool=(
            "This is a Python project (pyproject.toml). SHOULD use `uv run`/`uv add`, not pip/python directly."
        ),
        note_without_tool="This is a Python project (pyproject.toml).",
    ),
    # Future ecosystems (not implemented yet): TypeScript (package.json / pnpm), Rust (Cargo.toml / cargo).
)


def get_generic_tooling_note(workspace_roots: list[str]) -> str | None:
    """Return ecosystem tooling guidance for the first matching root/detector.

    Args:
        workspace_roots: List of workspace root paths to search.

    Returns:
        A note recommending the ecosystem's preferred tool (if installed) or
        just naming the ecosystem (if not); None if no root/detector matches.
    """
    for root in workspace_roots:
        for detector in _DETECTORS:
            if not (Path(root) / detector.marker_file).exists():
                continue
            if shutil.which(detector.command):
                return detector.note_with_tool
            return detector.note_without_tool
    return None


def resolve_tooling_notes(plugins: list[HooksPlugin], workspace_roots: list[str]) -> list[str]:
    """Merge plugin-supplied tooling notes with the generic ecosystem note.

    Args:
        plugins: Loaded plugin instances.
        workspace_roots: List of workspace root paths to search.

    Returns:
        Ordered notes: the generic note (unless a plugin replaces it), then
        replacing plugin notes, then additive plugin notes.
    """
    replacement_parts: list[str] = []
    additive_parts: list[str] = []
    suppress_generic = False
    for plugin in plugins:
        tooling_note = plugin.get_tooling_note(workspace_roots)
        if tooling_note is None:
            continue
        if tooling_note.replaces_generic:
            suppress_generic = True
            replacement_parts.append(tooling_note.note)
        else:
            additive_parts.append(tooling_note.note)

    notes: list[str] = []
    if not suppress_generic:
        generic = get_generic_tooling_note(workspace_roots)
        if generic:
            notes.append(generic)
    notes.extend(replacement_parts)
    notes.extend(additive_parts)
    return notes
