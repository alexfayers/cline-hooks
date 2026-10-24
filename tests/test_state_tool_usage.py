from __future__ import annotations

import json

import cline_hooks.state.tool_usage as tool_usage_module
from cline_hooks.state.tool_usage import HALF_LIFE_SECONDS, record_tool_use, top_tools

START = 1_000_000.0
FAR_FUTURE = START + 100 * HALF_LIFE_SECONDS


def test_the_most_used_tools_come_first_and_each_frontend_keeps_its_own() -> None:
    for tool in ("a", "b", "b", "c", "c", "c"):
        record_tool_use("pi", tool, START)
    record_tool_use("claude-code", "d", START)

    assert top_tools("pi", 2, START) == ["c", "b"]
    assert top_tools("claude-code", 5, START) == ["d"]


def test_old_use_counts_for_less_and_a_tool_decayed_away_is_forgotten() -> None:
    for _ in range(2):
        record_tool_use("pi", "old", START)
    record_tool_use("pi", "recent", START + 2 * HALF_LIFE_SECONDS)

    assert top_tools("pi", 2, START + 2 * HALF_LIFE_SECONDS) == ["recent", "old"]

    record_tool_use("pi", "kept", FAR_FUTURE)

    assert top_tools("pi", 5, FAR_FUTURE) == ["kept"]
    assert list(json.loads(tool_usage_module._USAGE_PATH.read_text(encoding="utf-8"))["pi"]) == ["kept"]
