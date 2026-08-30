"""Read context-token usage and assistant text from a Claude Code transcript JSONL file."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

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
    latest_usage: dict[str, Any] | None = None
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
    return _sum_context_fields(latest_usage)


def _sum_context_fields(usage: dict[str, Any]) -> int:
    """Sum the token fields that make up the context sent to the model."""
    total = 0
    for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            total += value
    return total


def get_turn_assistant_text(transcript_path: str) -> str:
    """Return this turn's main-thread assistant text from a transcript.

    Finds the last real user-authored prompt (skipping user entries that are
    only tool-result feedback) and joins every main-thread assistant text
    block written since then, so a dismissal made earlier in a multi-tool-call
    turn is caught, not just the final message.

    Args:
        transcript_path: Path to the transcript JSONL file.

    Returns:
        Newline-joined assistant text since the last user prompt, or "" if
        the file is unreadable, empty, or has no assistant text.
    """
    entries: list[dict[str, Any]] = []
    try:
        with Path(transcript_path).open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if isinstance(entry, dict):
                    entries.append(entry)
    except OSError:
        return ""

    last_user_index = -1
    for index, entry in enumerate(entries):
        if _is_user_prompt(entry):
            last_user_index = index

    texts: list[str] = []
    for entry in entries[last_user_index + 1 :]:
        if entry.get("type") != "assistant" or entry.get("isSidechain"):
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        texts.extend(
            block["text"]
            for block in content
            if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
        )

    return "\n".join(texts)


def _is_user_prompt(entry: dict[str, Any]) -> bool:
    """Check whether a transcript entry is a real user-authored prompt.

    A tool-result being fed back to the model is also a "user" entry, so it
    must be excluded to find the actual turn boundary.

    Args:
        entry: A parsed transcript JSONL entry.

    Returns:
        True if the entry is a user-authored prompt, not a tool result.
    """
    if entry.get("type") != "user" or entry.get("isSidechain"):
        return False
    message = entry.get("message")
    if not isinstance(message, dict):
        return False
    content = message.get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return not any(isinstance(block, dict) and block.get("type") == "tool_result" for block in content)
    return False


def _usage_from_line(line: str) -> dict[str, Any] | None:
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
    return _main_thread_usage(usage)


def _main_thread_usage(usage: dict[str, Any]) -> dict[str, Any]:
    """Return the true main-thread usage, unwrapping a server-tool roll-up."""
    iterations = usage.get("iterations")
    if isinstance(iterations, list):
        messages = [it for it in iterations if isinstance(it, dict) and it.get("type") == "message"]
        if messages:
            return messages[-1]
    return usage
