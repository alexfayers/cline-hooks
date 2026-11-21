"""Pi's transcript reader: its session JSONL, a tree of entries linked by `parentId`."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cline_hooks.core.transcript import TranscriptReader

if TYPE_CHECKING:
    from collections.abc import Iterator


class PiTranscriptReader(TranscriptReader):
    """Reads the active branch of pi's session JSONL."""

    def context_tokens(self, transcript_path: str) -> int | None:
        """Return None - pi's bridge reports the context usage itself.

        Returns:
            None, always.
        """
        return None

    def turn_assistant_text(self, transcript_path: str) -> str:
        """Return the assistant text written since the last user prompt on the active branch.

        Args:
            transcript_path: Path to the session JSONL file.

        Returns:
            Newline-joined assistant text, or "" if the file is unreadable or has none.
        """
        texts: list[str] = []
        for entry in _branch_from_leaf(transcript_path):
            role = _role(entry)
            if role == "user":
                break
            if role == "assistant":
                texts[:0] = _text_blocks(entry["message"])
        return "\n".join(texts)


def _branch_from_leaf(transcript_path: str) -> Iterator[dict[str, Any]]:
    """Yield the entries from the last entry back to the root, following `parentId`.

    Args:
        transcript_path: Path to the session JSONL file.

    Yields:
        Each entry on the active branch, newest first, or none if the file is unreadable.
    """
    with contextlib.suppress(OSError), Path(transcript_path).open("rb") as handle:
        offsets: dict[str, tuple[str | None, int]] = {}
        leaf_id: str | None = None
        offset = 0
        for line in handle:
            entry = _parse_entry(line)
            if entry is not None and entry.get("type") != "session" and isinstance(entry.get("id"), str):
                parent_id = entry.get("parentId")
                offsets[entry["id"]] = (parent_id if isinstance(parent_id, str) else None, offset)
                leaf_id = entry["id"]
            offset += len(line)
        seen: set[str] = set()
        while leaf_id in offsets and leaf_id not in seen:
            seen.add(leaf_id)
            leaf_id, start = offsets[leaf_id]
            handle.seek(start)
            entry = _parse_entry(handle.readline())
            if entry is not None:
                yield entry


def _parse_entry(line: bytes) -> dict[str, Any] | None:
    """Parse one JSONL line.

    Returns:
        The entry, or None if the line is not a JSON object.
    """
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    return entry if isinstance(entry, dict) else None


def _role(entry: dict[str, Any]) -> str | None:
    """Return the role of a message entry, or None for any other entry."""
    message = entry.get("message")
    if entry.get("type") != "message" or not isinstance(message, dict):
        return None
    role = message.get("role")
    return role if isinstance(role, str) else None


def _text_blocks(message: dict[str, Any]) -> list[str]:
    """Return the text of every text block in a message's content."""
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    ]
