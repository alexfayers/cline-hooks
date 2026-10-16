from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.protocol import get_protocol, set_protocol
from cline_hooks.frontends.pi.protocol import PiProtocol
from cline_hooks.plugins.startup_blocks import StartupBlocksPlugin
from cline_hooks.plugins.tool_usage import TOP_TOOLS, ToolUsagePlugin
from cline_hooks.state.tool_usage import top_tools

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.fixture
def pi(use_plugins: Callable[..., None]) -> None:
    use_plugins(StartupBlocksPlugin(), ToolUsagePlugin())
    set_protocol(PiProtocol())


def use(task_id: str, server: str, tool: str, **kwargs: object) -> None:
    collect_hook_results(
        load_plugins(),
        "TrackToolUse",
        task_id=task_id,
        tool_name="use_mcp_tool",
        parameters={"server_name": server, "tool_name": tool, "arguments": {}},
        mcp_tool_name=tool,
        **kwargs,
    )


def start(task_id: str = "next", source: str = "startup") -> list[str]:
    return collect_hook_results(
        load_plugins(), "TaskStart", task_id=task_id, workspace_roots=["/ws"], source=source
    ).notes


def note_for(*names: str) -> str:
    assert PiProtocol.frontend_spec is not None
    assert PiProtocol.frontend_spec.tool_hint is not None
    return PiProtocol.frontend_spec.tool_hint(names)


@pytest.mark.usefixtures("pi")
class TestStartupBlock:
    def test_a_later_session_is_told_the_read_tools_used_before_in_the_frontends_own_words(self) -> None:
        assert start() == []
        collect_hook_results(
            load_plugins(), "TrackToolUse", task_id="s0", tool_name="read", parameters={"path": "a"}, mcp_tool_name=None
        )
        reads = ("read_graph", "IssueGetItem")
        writes = ("create_entities", "set_metadata", "IssueUpdateItem", "PullAddComment", "IssueWriteActions", "send")
        for tool in reads + writes:
            use(f"s-{tool}", "srv", tool)
        use("s1", "send_mail", "read_inbox")

        assert start() == [note_for("mcp__send_mail__read_inbox", "mcp__srv__IssueGetItem", "mcp__srv__read_graph")]

    def test_names_are_sorted_and_only_the_highest_scoring_are_listed(self) -> None:
        names = [f"tool_{index:02d}" for index in range(TOP_TOOLS + 1)]
        for name in reversed(names):
            use(f"first-{name}", "srv", name)
        for name in names[1:]:
            use(f"second-{name}", "srv", name)

        assert start() == [note_for(*(f"mcp__srv__{name}" for name in names[1:]))]

    def test_a_tight_budget_drops_the_lowest_scoring_names_before_the_block(self) -> None:
        use("s1", "srv", "aaa")
        use("s2", "srv", "aaa")
        use("s3", "srv", "bbb")
        [block] = ToolUsagePlugin().startup_blocks(["/ws"])

        assert block.body(len(note_for("mcp__srv__aaa"))) == note_for("mcp__srv__aaa")

    def test_each_session_counts_a_tool_once_until_it_restarts(self) -> None:
        for _ in range(3):
            use("s1", "srv", "once")
        start("s1", source="resume")
        use("s1", "srv", "once")
        use("s2", "srv", "twice")
        start("s2")
        use("s2", "srv", "twice")
        use("s3", "srv", "thrice")
        use("s4:agent", "srv", "thrice", agent_id="agent")
        use("s5", "srv", "thrice")

        assert top_tools("pi", 5, time.time()) == ["mcp__srv__thrice", "mcp__srv__twice", "mcp__srv__once"]


def test_a_frontend_with_no_tool_hint_gets_no_block_and_records_nothing(use_plugins: Callable[..., None]) -> None:
    use_plugins(StartupBlocksPlugin(), ToolUsagePlugin())
    spec = get_protocol().frontend_spec
    assert spec is not None
    assert spec.tool_hint is None
    use("s1", "memory", "read_graph")

    assert start() == []
    assert top_tools(spec.name, 5, time.time()) == []
