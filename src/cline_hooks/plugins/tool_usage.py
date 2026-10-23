"""List the MCP tools a user calls most at session start."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import time
from typing import TYPE_CHECKING

from cline_hooks.core.hook_kwargs import TrackToolUseKwargs
from cline_hooks.core.parameters import McpToolUse
from cline_hooks.core.payload import StandardPayloadProtocol
from cline_hooks.core.plugin import HookResult, HooksPlugin, hookimpl
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.state import PluginStateStore
from cline_hooks.core.vocabulary import NO_RESET_TASK_START_SOURCES, CanonicalHook, PluginScope
from cline_hooks.plugins.startup_blocks import StartupBlock
from cline_hooks.state.tool_usage import record_tool_use, top_tools

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    import logging

TOP_TOOLS = 15
BLOCK_ORDER = 900
_NAME_WORDS = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
_WRITE_WORD = re.compile(
    r"add|append|assign|close|comment|create|delete|edit|merge|modify|patch|post|publish|push|put|remove|reply|send"
    r"|set|submit|update|upload|write"
)


@dataclass
class _SeenTools:
    names: list[str] = field(default_factory=list)


_seen = PluginStateStore("tool-usage-seen.json", _SeenTools)


def _claude_code_hint(names: Sequence[str]) -> str:
    return (
        "MCP tools this user often calls (not a full list). "
        f"Add these to your one ToolSearch `select:` call: `{','.join(names)}`."
    )


def _pi_hint(names: Sequence[str]) -> str:
    calls = ", ".join(f"`tools.{name}`" for name in names)
    return f"MCP tools this user often calls (not a full list): {calls}"


_TOOL_HINTS: dict[str, Callable[[Sequence[str]], str]] = {"claude-code": _claude_code_hint, "pi": _pi_hint}


def _live_hint() -> tuple[Callable[[Sequence[str]], str], str, type[StandardPayloadProtocol]] | None:
    """Return the live frontend's tool hint, name and protocol, or None where it has no tool hint."""
    protocol = type(get_protocol())
    spec = protocol.frontend_spec
    if spec is None or spec.name not in _TOOL_HINTS or not issubclass(protocol, StandardPayloadProtocol):
        return None
    return _TOOL_HINTS[spec.name], spec.name, protocol


def _is_write_tool(tool_name: str) -> bool:
    """Return whether any word of a snake_case or CamelCase tool name is a write verb."""
    return any(_WRITE_WORD.fullmatch(word.lower()) for word in _NAME_WORDS.findall(tool_name))


def _body(hint: Callable[[Sequence[str]], str], names: list[str], room: int | None) -> str:
    """Return the wording of as many of the best names as fit in the room."""
    count = len(names)
    while count > 1 and room is not None and len(hint(sorted(names[:count]))) > room:
        count -= 1
    return hint(sorted(names[:count]))


def _first_use(task_id: str, name: str) -> bool:
    """Return whether a session uses a tool for the first time, marking it used."""

    def mark(seen: _SeenTools) -> bool:
        if name in seen.names:
            return False
        seen.names.append(name)
        return True

    return _seen.update(task_id, mark)


class ToolUsagePlugin(HooksPlugin):
    """Records MCP tool use and lists the most used tools."""

    @hookimpl
    def startup_blocks(self, workspace_roots: list[str]) -> list[StartupBlock]:
        """Return the block naming the MCP tools this user calls most on this frontend, or none."""
        live = _live_hint()
        if live is None or not (names := top_tools(live[1], TOP_TOOLS, time.time())):
            return []
        return [
            StartupBlock(
                title="MCP tools this user often calls",
                replaces="search for the MCP tools this user calls most",
                body=lambda room: _body(live[0], names, room),
                order=BLOCK_ORDER,
            )
        ]

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Record the first use of each read-only MCP tool in a session.

        Returns:
            None.
        """
        if hook_name == CanonicalHook.TASK_START:
            task_id = kwargs.get("task_id")
            if isinstance(task_id, str) and kwargs.get("source") not in NO_RESET_TASK_START_SOURCES:
                _seen.reset(task_id)
            return None
        live = _live_hint()
        if hook_name != PluginScope.TRACK_TOOL_USE or live is None:
            return None
        kw = TrackToolUseKwargs.build(kwargs)
        tool = McpToolUse.build(kw.parameters)
        name = f"{live[2].mcp_prefix}{tool.server_name}{live[2].mcp_separators[0]}{tool.tool_name}"
        if kw.mcp_tool_name is not None and not _is_write_tool(tool.tool_name) and _first_use(kw.task_id, name):
            record_tool_use(live[1], name, time.time())
        return None
