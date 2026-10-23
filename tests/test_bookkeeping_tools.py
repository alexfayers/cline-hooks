from __future__ import annotations

import pytest

from cline_hooks.core.payload import map_tool_name
from cline_hooks.core.vocabulary import BOOKKEEPING_TOOLS, KNOWN_TOOLS
from cline_hooks.frontends.claude_code.protocol import ClaudeCodeProtocol
from cline_hooks.frontends.pi.protocol import PiProtocol


@pytest.mark.parametrize(
    ("protocol_cls", "native_name"),
    [
        (ClaudeCodeProtocol, "TaskCreate"),
        (ClaudeCodeProtocol, "TaskUpdate"),
        (ClaudeCodeProtocol, "TaskList"),
        (ClaudeCodeProtocol, "TaskGet"),
        (ClaudeCodeProtocol, "ToolSearch"),
        (PiProtocol, "tower_do"),
        (PiProtocol, "tower_do_patch"),
        (PiProtocol, "tower_do_status"),
        (PiProtocol, "tower_do_talk"),
    ],
)
def test_task_tracking_tools_map_to_bookkeeping(protocol_cls: type, native_name: str) -> None:
    assert map_tool_name(native_name, protocol_cls) in BOOKKEEPING_TOOLS


def test_bookkeeping_tools_stay_outside_the_tools_handlers_act_on() -> None:
    assert not BOOKKEEPING_TOOLS & KNOWN_TOOLS
