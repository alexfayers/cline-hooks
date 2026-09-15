"""Antigravity's transcript reader: its per-conversation JSONL log."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cline_hooks.core.transcript import TranscriptReader

_USER_SOURCE = "USER_EXPLICIT"
_MODEL_SOURCE = "MODEL"


def _read_entries(transcript_path: str) -> list[dict[str, Any]]:
    """Parse a JSONL transcript, skipping any line that isn't a JSON object.

    Args:
        transcript_path: Path to the transcript, which Antigravity may report
            with a leading `~`.

    Returns:
        The parsed entries, or [] if the file cannot be read.
    """
    entries: list[dict[str, Any]] = []
    try:
        with Path(transcript_path).expanduser().open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(entry, dict):
                    entries.append(entry)
    except OSError:
        return []
    return entries


class AntigravityTranscriptReader(TranscriptReader):
    """Reads Antigravity's JSONL transcript, one JSON entry per line.

    Antigravity documents the transcript's path but not its entries, which are
    read as carrying a `source` of USER_EXPLICIT, MODEL or SYSTEM, and a model
    entry's text as a `content` string. That shape is unverified.
    """

    def context_tokens(self, transcript_path: str) -> int | None:
        """Return None - Antigravity's transcript reports no token counts.

        Returns:
            None, always.
        """
        return None

    def turn_assistant_text(self, transcript_path: str) -> str:
        """Return this turn's model text from an Antigravity transcript.

        Args:
            transcript_path: Path to the transcript JSONL file.

        Returns:
            Newline-joined model text written since the last explicit user
            message, or "" if the file is unreadable or holds no model text.
        """
        entries = _read_entries(transcript_path)

        last_user_index = -1
        for index, entry in enumerate(entries):
            if entry.get("source") == _USER_SOURCE:
                last_user_index = index

        return "\n".join(
            entry["content"]
            for entry in entries[last_user_index + 1 :]
            if entry.get("source") == _MODEL_SOURCE
            and isinstance(entry.get("content"), str)
        )
