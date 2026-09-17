from __future__ import annotations

from typing import cast

from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.vocabulary import CanonicalHook
from cline_hooks.handlers.git_context import get_git_context


def _git_context_guard(**kwargs: object) -> HookResult | None:
    """Return the git branch/dirty/commits/TODO.md context note, if any.

    Args:
        **kwargs: The TaskStart/TaskResume dispatch kwargs (workspace_roots, ...).

    Returns:
        A HookResult carrying the git context note, or None if no repo found.
    """
    workspace_roots = cast("list[str]", kwargs.get("workspace_roots") or [])
    git_context = get_git_context(workspace_roots)
    if git_context is None:
        return None
    return HookResult(notes=[git_context])


class SessionContextPlugin(HooksPlugin):
    """Bundled plugin surfacing informational session-context notes."""

    def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
        """Dispatch TaskStart and TaskResume events to the git-context note.

        Args:
            hook_name: The hook or plugin-scope name.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult carrying the git context note, or None.
        """
        if hook_name in {CanonicalHook.TASK_START, CanonicalHook.TASK_RESUME}:
            return _git_context_guard(**kwargs)
        return None
