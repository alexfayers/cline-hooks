from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from cline_hooks.core.transcript import get_context_tokens

if TYPE_CHECKING:
    from pathlib import Path


def _assistant(
    *,
    input_tokens: int = 0,
    cache_read: int = 0,
    cache_creation: int = 0,
    sidechain: bool = False,
) -> dict[str, Any]:
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {
            "role": "assistant",
            "usage": {
                "input_tokens": input_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
            },
        },
    }


def _write_jsonl(path: Path, entries: list[dict[str, Any]]) -> str:
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    return str(path)


class TestGetContextTokens:
    def test_sums_last_assistant_usage(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [_assistant(input_tokens=10, cache_read=200, cache_creation=5)],
        )
        assert get_context_tokens(path) == 215

    def test_picks_last_assistant_entry(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [
                _assistant(cache_read=500),
                _assistant(input_tokens=1, cache_read=300),
            ],
        )
        assert get_context_tokens(path) == 301

    def test_ignores_sidechain_assistant_entries(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [
                _assistant(cache_read=100),
                _assistant(cache_read=999, sidechain=True),
            ],
        )
        assert get_context_tokens(path) == 100

    def test_ignores_non_assistant_lines(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [
                _assistant(cache_read=100),
                {"type": "user", "message": {"role": "user", "usage": {"input_tokens": 9}}},
                {"type": "system", "message": {}},
            ],
        )
        assert get_context_tokens(path) == 100

    def test_missing_usage_keys_default_to_zero(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text(
            json.dumps({
                "type": "assistant",
                "isSidechain": False,
                "message": {"role": "assistant", "usage": {"cache_read_input_tokens": 50}},
            }),
            encoding="utf-8",
        )
        assert get_context_tokens(str(path)) == 50

    def test_nonexistent_path_returns_none(self, tmp_path: Path) -> None:
        assert get_context_tokens(str(tmp_path / "missing.jsonl")) is None

    def test_malformed_line_is_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text("not json\n" + json.dumps(_assistant(cache_read=42)), encoding="utf-8")
        assert get_context_tokens(str(path)) == 42

    def test_empty_file_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "t.jsonl"
        path.write_text("", encoding="utf-8")
        assert get_context_tokens(str(path)) is None

    def test_no_assistant_with_usage_returns_none(self, tmp_path: Path) -> None:
        path = _write_jsonl(
            tmp_path / "t.jsonl",
            [{"type": "user", "message": {"role": "user"}}],
        )
        assert get_context_tokens(path) is None
