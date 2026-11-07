from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.core.plugin import HookResult, HooksPlugin, is_subagent
from cline_hooks.core.vocabulary import CanonicalHook, PluginScope
from cline_hooks.plugins.nudges import has_edited
from cline_hooks.state.memory import has_memory_writes
from cline_hooks.state.skills import is_session_end_skill

if TYPE_CHECKING:
    import logging

_FAILURE_PERSIST_NOTE = (
    "A tool just failed. Where the failure was your own mistake and you have fixed it, MUST persist the mistake "
    "and the fix to memory (and propose a rule/skill change where it reveals a missing process step)."
)

_MEMORY_WARNING = (
    "WARNING: No memory writes have been made this session. "
    "You MUST persist your work to memory NOW before completing. "
    "Knowledge not persisted is permanently lost."
)


def _owes_memory_write(task_id: str, kwargs: dict[str, object]) -> bool:
    """Check whether a main-agent session has edited files without writing memory.

    Args:
        task_id: The session or task identifier.
        kwargs: The raw keyword arguments passed to on_hook.

    Returns:
        True if the session edited files, wrote no memory, and is not a subagent.
    """
    return not is_subagent(kwargs) and has_edited(task_id) and not has_memory_writes(task_id)


class PersistencePlugin(HooksPlugin):
    """Nudges toward memory persistence on tool failure and at session end."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Emit a persist-to-memory nudge on tool failure or session end.

        Args:
            hook_name: The hook event or plugin-scope name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult carrying the relevant nudge, or None.
        """
        if hook_name == PluginScope.TOOL_FAILED:
            if is_subagent(kwargs):
                return None
            logger.debug("Fired persist-to-memory nudge after tool failure")
            return HookResult(notes=[_FAILURE_PERSIST_NOTE])
        if hook_name == CanonicalHook.POST_TOOL_USE:
            tool_name = kwargs.get("tool_name")
            parameters = kwargs.get("parameters")
            task_id = kwargs.get("task_id")
            if (
                isinstance(tool_name, str)
                and isinstance(parameters, dict)
                and isinstance(task_id, str)
                and is_session_end_skill(tool_name, parameters)
                and _owes_memory_write(task_id, kwargs)
            ):
                logger.debug("Fired no-memory-writes warning at session end")
                return HookResult(notes=[_MEMORY_WARNING])
        return None
