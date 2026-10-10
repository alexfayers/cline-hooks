from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_hooks.handlers.commands import ParsedCommand

_HERDR_TIMEOUT_SECONDS = 5


def removed_worktree_paths(commands: list[ParsedCommand]) -> list[str]:
    """Return the path arguments of every `git worktree remove` command.

    Returns:
        The path words that follow `worktree remove`, flags excluded.
    """
    paths: list[str] = []
    for cmd in commands:
        if cmd.name == "git" and "worktree" in cmd.args:
            rest = cmd.args[cmd.args.index("worktree") + 1 :]
            if rest[:1] == ["remove"]:
                paths.extend(rest[1:])
    return paths


def _linked_workspaces() -> dict[str, str]:
    """Map each Herdr workspace's checkout path to its id.

    Returns:
        The mapping, or empty if herdr is unavailable or fails.
    """
    if not shutil.which("herdr"):
        return {}
    try:
        completed = subprocess.run(
            ["herdr", "workspace", "list"],  # ruff: ignore[start-process-with-partial-path]
            capture_output=True,
            text=True,
            timeout=_HERDR_TIMEOUT_SECONDS,
            check=False,
        )
        workspaces = json.loads(completed.stdout)["result"]["workspaces"]
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return {}
    if completed.returncode != 0:
        return {}
    return {
        os.path.normpath(workspace["worktree"]["checkout_path"]): workspace["workspace_id"]
        for workspace in workspaces
        if "checkout_path" in (workspace.get("worktree") or {})
    }


def workspace_linking(paths: list[str], cwd: str) -> str | None:
    """Return the id of a Herdr workspace linked to any of the given paths, else None.

    Returns:
        The first matching workspace id, or None when none match or herdr cannot be queried.
    """
    if not paths:
        return None
    linked = _linked_workspaces()
    for path in paths:
        resolved = os.path.normpath(Path(cwd) / Path(path).expanduser())
        if resolved in linked:
            return linked[resolved]
    return None
