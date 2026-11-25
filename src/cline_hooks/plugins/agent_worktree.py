from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import git

from cline_hooks.core.hook_kwargs import PreToolUseKwargs
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.vocabulary import FILE_EDIT_TOOLS, CanonicalHook

if TYPE_CHECKING:
    import logging

WRITER_ROLE = "writer"


def _worktree_path(path: Path, worktree: str) -> Path | None:
    """Return the same file under the worktree, or None where the path is not in its repo's primary checkout."""
    try:
        repo = git.Repo(worktree, search_parent_directories=True)
    except (git.InvalidGitRepositoryError, git.NoSuchPathError):
        return None
    common_dir = Path(repo.common_dir).resolve()
    top = Path(repo.working_tree_dir or "").resolve()
    primary = common_dir.parent
    if common_dir.name != ".git" or not path.is_relative_to(primary) or path.is_relative_to(top):
        return None
    return top / path.relative_to(primary)


class AgentWorktreePlugin(HooksPlugin):
    """Bundled plugin sending a pi writer's file edit in the primary checkout to its worktree."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Return the writer's complete tool input with the edited path moved into its worktree.

        Returns:
            A HookResult carrying the rewritten input, or None.
        """
        spec = get_protocol().frontend_spec
        if hook_name != CanonicalHook.PRE_TOOL_USE or spec is None or spec.name != "pi":
            return None
        call = PreToolUseKwargs.build(kwargs)
        path = call.tool_input.get("path")
        if (
            call.agent_type != WRITER_ROLE
            or call.tool_name not in FILE_EDIT_TOOLS
            or not (isinstance(path, str) and call.workspace_roots)
        ):
            return None
        worktree = call.workspace_roots[0]
        redirected = _worktree_path(Path(worktree, Path(path).expanduser()).resolve(), worktree)
        if redirected is None:
            return None
        logger.debug("Redirected a writer edit from the primary checkout to its worktree")
        return HookResult(
            updated_input={**call.tool_input, "path": str(redirected)},
            notes=[f"Redirected your edit of {path} to {redirected}. MUST edit files under your worktree."],
        )
