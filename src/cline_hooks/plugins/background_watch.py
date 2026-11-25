from __future__ import annotations

import re
import shlex
from typing import TYPE_CHECKING

from cline_hooks.core.hook_kwargs import PreShellKwargs
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.vocabulary import SHELL_TOOLS, PluginScope

if TYPE_CHECKING:
    import logging

_WATCH_COMMAND = re.compile(r"(?:^|[;&|(]\s*)llm-prompts\s+watch\s")


def _detached(command: str) -> str:
    """Return a command that runs `command` detached, writing its output to a temp file, and returns at once."""
    script = shlex.quote(f'(\n{command}\n) >"$0" 2>&1 </dev/null &')
    return f'log=$(mktemp) && bash -c {script} "$log" && echo "Running in the background. Its output is in $log"'


class BackgroundWatchPlugin(HooksPlugin):
    """Bundled plugin moving a pi fork's foreground `llm-prompts watch` call to the background.

    It acts on the PreShell scope and runs last, so every guard checks the batch as sent.
    """

    runs_last = True

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Return the fork's bash input with its watch command run detached.

        Returns:
            A HookResult carrying the complete rewritten input, or None.
        """
        spec = get_protocol().frontend_spec
        if hook_name != PluginScope.PRE_SHELL or spec is None or spec.name != "pi":
            return None
        call = PreShellKwargs.build(kwargs)
        if not call.agent_id or call.tool_name not in SHELL_TOOLS or not _WATCH_COMMAND.search(call.command):
            return None
        logger.debug("Moved a fork's watch to the background")
        return HookResult(updated_input={**call.parameters, "command": _detached(call.command)})
