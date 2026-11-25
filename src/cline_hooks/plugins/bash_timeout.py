from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.core.hook_kwargs import PreToolUseKwargs
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.vocabulary import SHELL_TOOLS, CanonicalHook

if TYPE_CHECKING:
    import logging

DEFAULT_BASH_TIMEOUT_SECONDS = 900


class BashTimeoutPlugin(HooksPlugin):
    """Bundled plugin giving a pi bash call that sets no timeout a default one."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Return the default timeout for a pi bash call that has none.

        Returns:
            A HookResult carrying the timeout, or None.
        """
        spec = get_protocol().frontend_spec
        if hook_name != CanonicalHook.PRE_TOOL_USE or spec is None or spec.name != "pi":
            return None
        call = PreToolUseKwargs.build(kwargs)
        if call.tool_name not in SHELL_TOOLS or call.parameters.get("timeout") is not None:
            return None
        return HookResult(updated_input={**call.parameters, "timeout": DEFAULT_BASH_TIMEOUT_SECONDS})
