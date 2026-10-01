from __future__ import annotations

import contextlib
from unittest.mock import patch

from cline_hooks.core.models import HookInputPreCompact, PreCompactFields
from cline_hooks.core.plugin import HookResult
from cline_hooks.handlers.pre_compact import handle_pre_compact


def _pre_compact() -> HookInputPreCompact:
    return HookInputPreCompact(
        taskId="task-1",
        workspaceRoots=[],
        hookName="PreCompact",
        preCompact=PreCompactFields(conversationLength=10, estimatedTokens=1000),
    )


class TestForwardsStateKey:
    def test_subagent_task_id_is_the_per_agent_state_key(self) -> None:
        captured: dict[str, object] = {}

        def _fake_collect(_plugins: object, _hook_name: str, **kwargs: object) -> HookResult:
            captured.update(kwargs)
            return HookResult()

        hook = _pre_compact()
        hook.agentId = "agent-7"
        with (
            patch("cline_hooks.handlers.pre_compact.collect_hook_results", side_effect=_fake_collect),
            patch("builtins.print"),
            contextlib.suppress(SystemExit),
        ):
            handle_pre_compact(hook)
        assert captured.get("task_id") == "task-1:agent-7"
