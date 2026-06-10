"""Read context-token usage from a Claude Code transcript JSONL file."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger("hooks")


def get_context_tokens(transcript_path: str) -> int | None:
    """Return the current context-token count from a transcript file.

    Reads the transcript JSONL and finds the last main-thread (non-sidechain)
    assistant message carrying usage data. The most recent assistant call's
    input + cache-read + cache-creation tokens are exactly the context that was
    sent to the model, so the last such entry reflects current context size.

    Args:
        transcript_path: Path to the transcript JSONL file.

    Returns:
        The context-token count, or None if the file is unreadable or contains
        no main-thread assistant message with usage data.
    """
    latest_usage: dict[str, int] | None = None
    try:
        with Path(transcript_path).open(encoding="utf-8") as handle:
            for line in handle:
                usage = _usage_from_line(line)
                if usage is not None:
                    latest_usage = usage
    except OSError:
        return None

    if latest_usage is None:
        return None
    return (
        latest_usage.get("input_tokens", 0)
        + latest_usage.get("cache_read_input_tokens", 0)
        + latest_usage.get("cache_creation_input_tokens", 0)
    )


def _usage_from_line(line: str) -> dict[str, int] | None:
    """Extract usage data from a transcript line if it is a main-thread assistant message.

    Args:
        line: A single JSONL line from the transcript.

    Returns:
        The usage dict, or None if the line is not a qualifying assistant message.
    """
    try:
        entry = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(entry, dict) or entry.get("type") != "assistant" or entry.get("isSidechain"):
        return None
    message = entry.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    return usage
