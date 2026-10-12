"""Pi's transcript reader: its session JSONL, a tree of entries linked by `parentId`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cline_hooks.core.transcript import TranscriptReader


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
        for entry in reversed(_active_branch(transcript_path)):
            role = _role(entry)
            if role == "user":
                break
            if role == "assistant":
                texts[:0] = _text_blocks(entry["message"])
        return "\n".join(texts)


def _active_branch(transcript_path: str) -> list[dict[str, Any]]:
    """Return the entries from the root to the last entry, following `parentId`.

    Args:
        transcript_path: Path to the session JSONL file.

    Returns:
        The active branch in order, or [] if the file is unreadable.
    """
    entries: dict[str, dict[str, Any]] = {}
    leaf_id: str | None = None
    try:
        with Path(transcript_path).open(encoding="utf-8") as handle:
            for line in handle:
                entry = _parse_entry(line)
                if entry is not None and entry.get("type") != "session" and isinstance(entry.get("id"), str):
                    entries[entry["id"]] = entry
                    leaf_id = entry["id"]
    except OSError:
        return []

    branch: list[dict[str, Any]] = []
    while leaf_id in entries and entries[leaf_id] not in branch:
        branch.append(entries[leaf_id])
        leaf_id = entries[leaf_id].get("parentId")
    return branch[::-1]


def _parse_entry(line: str) -> dict[str, Any] | None:
    """Parse one JSONL line.

    Returns:
        The entry, or None if the line is not a JSON object.
    """
    try:
        entry = json.loads(line)
    except json.JSONDecodeError:
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
