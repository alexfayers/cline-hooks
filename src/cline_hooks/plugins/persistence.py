from __future__ import annotations

from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.vocabulary import CanonicalHook, PluginScope
from cline_hooks.state.memory import has_memory_writes
from cline_hooks.state.skills import is_session_end_skill

_FAILURE_PERSIST_NOTE = (
    "A tool just failed. When you fix this, MUST persist what went wrong and the fix "
    "to memory (and to rules/skills where it reveals a missing process step)."
)

_MEMORY_WARNING = (
    "WARNING: No memory writes have been made this session. "
    "You MUST persist your work to memory NOW before completing. "
    "Knowledge not persisted is permanently lost."
)


class PersistencePlugin(HooksPlugin):
    """Nudges toward memory persistence on tool failure and at session end."""

    def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
        """Emit a persist-to-memory nudge on tool failure or session end.

        Args:
            hook_name: The hook event or plugin-scope name.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult carrying the relevant nudge, or None.
        """
        if hook_name == PluginScope.TOOL_FAILED:
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
                and not has_memory_writes(task_id)
            ):
                return HookResult(notes=[_MEMORY_WARNING])
        return None
