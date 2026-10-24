"""Decayed per-frontend scores of MCP tool use."""

from __future__ import annotations

from typing import cast

from cline_hooks.state.jsonfile import read_json, updated_json
from cline_hooks.state.paths import get_data_dir

_USAGE_PATH = get_data_dir() / "tool-usage.json"

HALF_LIFE_SECONDS = 14 * 24 * 60 * 60
SCORE_FLOOR = 0.1

type _Usage = dict[str, dict[str, dict[str, float]]]


def _scores(usage: dict[str, dict[str, float]], now: float) -> dict[str, float]:
    """Return each tool's score decayed to a time, leaving out those below the floor."""
    decayed = {
        name: entry["score"] * float(0.5 ** (max(now - entry["last"], 0.0) / HALF_LIFE_SECONDS))
        for name, entry in usage.items()
    }
    return {name: score for name, score in decayed.items() if score >= SCORE_FLOOR}


def record_tool_use(frontend: str, tool: str, now: float) -> None:
    """Add one use of a tool, by its name on a frontend, at a time in epoch seconds, to its score."""
    with updated_json(_USAGE_PATH, cast("_Usage", {})) as data:
        scores = _scores(data.get(frontend, {}), now)
        scores[tool] = scores.get(tool, 0.0) + 1.0
        data[frontend] = {name: {"score": score, "last": now} for name, score in scores.items()}


def top_tools(frontend: str, limit: int, now: float) -> list[str]:
    """Return up to `limit` of a frontend's highest-scoring tools at a time, best first."""
    scores = _scores(read_json(_USAGE_PATH, cast("_Usage", {})).get(frontend, {}), now)
    return sorted(scores, key=lambda name: (-scores[name], name))[:limit]
