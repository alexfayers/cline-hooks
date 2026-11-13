from __future__ import annotations

import os
from typing import TYPE_CHECKING, cast

from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.vocabulary import PluginScope
from cline_hooks.handlers.commands import extract_commands, is_git_push
from cline_hooks.handlers.herdr_guard import removed_worktree_paths, workspace_linking
from cline_hooks.handlers.push_guard import marker_above_repo
from cline_hooks.handlers.search_scope import MAX_SCAN_ENTRIES, MAX_SCAN_SECONDS, find_oversized_search

if TYPE_CHECKING:
    import logging


def _pre_shell_guard(logger: logging.Logger, **kwargs: object) -> HookResult | None:
    """Block a git push inside a managed workspace, a linked worktree removal, or an oversized recursive search.

    Args:
        logger: This plugin's hook-scoped child logger.
        **kwargs: The PreShell dispatch kwargs (command, workspace_roots).

    Returns:
        A blocking HookResult for a blocked push, a linked worktree removal or an oversized search, or None.
    """
    command = cast("str", kwargs.get("command") or "")
    workspace_roots = cast("list[str]", kwargs.get("workspace_roots") or [])

    import bashlex.errors  # ruff: ignore[import-outside-top-level]

    try:
        parsed = bashlex.parse(command)
    except (bashlex.errors.ParsingError, NotImplementedError):
        return None
    commands = extract_commands(parsed)

    if is_git_push(commands):
        marker = marker_above_repo(workspace_roots)
        if marker:
            logger.debug("Blocked git push: repo is inside a managed workspace")
            return HookResult(
                block=(
                    f"git push is blocked here: this repository is inside a managed "
                    f"workspace (a '{marker}' entry was found at or above the repo root). "
                    f"MUST use the workspace's own review/submit workflow instead of "
                    f"pushing directly."
                )
            )

    session_cwd = workspace_roots[0] if workspace_roots else os.getcwd()  # ruff: ignore[os-getcwd]
    workspace_id = workspace_linking(removed_worktree_paths(commands), session_cwd)
    if workspace_id:
        logger.debug("Blocked git worktree remove: a Herdr workspace links the path")
        return HookResult(
            block=(
                f"git worktree remove is blocked: Herdr workspace {workspace_id} links this worktree path. "
                f"Once no live agent runs there, MUST close it with `herdr workspace close {workspace_id}` "
                f"and then retry."
            )
        )
    scope = find_oversized_search(commands, session_cwd)
    if scope:
        logger.debug("Blocked oversized recursive search")
        return HookResult(
            block=(
                f"`{scope.tool}` would recursively search `{', '.join(scope.roots)}`, which is the "
                f"filesystem root, the home directory, or a tree over {MAX_SCAN_ENTRIES:,} entries or "
                f"{MAX_SCAN_SECONDS}s to list. MUST narrow the search path to the specific repo or "
                f"package directory you need, or bound the depth (e.g. `find -maxdepth 2`, "
                f"`rg --max-depth 2`)."
            )
        )
    return None


class ShellGuardsPlugin(HooksPlugin):
    """Bundled plugin enforcing shell-command guards."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Dispatch PreShell events to the shell-command guards.

        Args:
            hook_name: The hook or plugin-scope name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult with a block reason or notes, or None.
        """
        if hook_name == PluginScope.PRE_SHELL:
            return _pre_shell_guard(logger, **kwargs)
        return None
