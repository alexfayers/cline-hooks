from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from cline_hooks.core.models import HookInput, HookInputPostToolUse
from cline_hooks.core.plugin import HooksPlugin, hookimpl
from cline_hooks.core.protocol import RawPayload
from cline_hooks.frontends.cline import ClineProtocol
from cline_hooks.handlers.post_tool_use import handle_post_tool_use
from cline_hooks.plugins.research import ResearchPlugin, get_research

if TYPE_CHECKING:
    from collections.abc import Callable

_TASK = "task-1"


def _post_tool_use(tool_name: str, parameters: dict[str, object]) -> None:
    data = {
        "clineVersion": "1.0",
        "timestamp": "2024-01-01T00:00:00Z",
        "taskId": _TASK,
        "userId": "user-1",
        "workspaceRoots": ["/workspace"],
        "hookName": "PostToolUse",
        "postToolUse": {
            "toolName": tool_name,
            "parameters": parameters,
            "success": True,
            "executionTimeMs": 10,
            "result": None,
        },
    }
    hook: HookInput = ClineProtocol().parse(RawPayload.from_stdin(json.dumps(data)))
    assert isinstance(hook, HookInputPostToolUse)
    handle_post_tool_use(hook)


def _contributor(tools: dict[str, Callable[[dict[str, Any]], str]]) -> HooksPlugin:
    class Contributor(HooksPlugin):
        @hookimpl
        def research_tools(self) -> dict[str, Callable[[dict[str, Any]], str]]:
            return tools

    return Contributor()


class TestContributedResearchTools:
    def test_contributed_tool_is_recorded_with_the_extractor_detail(self, use_plugins: Callable[..., None]) -> None:
        use_plugins(ResearchPlugin(), _contributor({"fake_search": lambda arguments: str(arguments["query"])}))
        _post_tool_use("fake_search", {"query": "pluggy"})
        assert get_research(_TASK) == [{"tool": "fake_search", "detail": "pluggy"}]

    def test_external_extractor_wins_over_bundled_for_the_same_tool(self, use_plugins: Callable[..., None]) -> None:
        use_plugins(ResearchPlugin(), _contributor({"web_fetch": lambda arguments: f"external {arguments['url']}"}))
        _post_tool_use("web_fetch", {"url": "https://example.com/docs"})
        assert get_research(_TASK) == [{"tool": "web_fetch", "detail": "external https://example.com/docs"}]
