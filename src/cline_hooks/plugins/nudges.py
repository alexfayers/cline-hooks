from __future__ import annotations

import contextlib
from dataclasses import dataclass
import random
import re

import git
import git.exc

from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.state import PluginStateStore
from cline_hooks.core.timing import local_now
from cline_hooks.core.vocabulary import (
    FILE_EDIT_TOOLS,
    NO_RESET_TASK_START_SOURCES,
    CanonicalHook,
)
from cline_hooks.state.agents import agent_use_count
from cline_hooks.state.retrospective import record_session
from cline_hooks.state.skills import is_wrap_up_skill


@dataclass
class _TurnsState:
    """Per-session user-prompt turn count."""

    count: int = 0


_store: PluginStateStore[_TurnsState] = PluginStateStore("turns-state.json", _TurnsState)

_SCOPE_CHECK_THRESHOLD = 80
_REMINDER_INTERVAL = 40
_AGENT_NUDGE_THRESHOLD = 50


def increment(task_id: str) -> int:
    """Increment and return the turn count for a session.

    Args:
        task_id: The session or task identifier.

    Returns:
        The new turn count after incrementing.
    """
    state = _store.get(task_id)
    state.count += 1
    _store.set(task_id, state)
    return state.count


def should_remind(turn_count: int) -> bool:
    """Check whether the current turn count should trigger a scope reminder.

    Triggers at the threshold, then every REMINDER_INTERVAL turns after.

    Args:
        turn_count: The current turn count.

    Returns:
        True if a scope-check reminder should be shown.
    """
    if turn_count < _SCOPE_CHECK_THRESHOLD:
        return False
    return (turn_count - _SCOPE_CHECK_THRESHOLD) % _REMINDER_INTERVAL == 0


def should_nudge_agents(turn_count: int, agent_count: int) -> bool:
    """Check whether to nudge for more subagent fan-out, based on usage rate.

    Checked every AGENT_NUDGE_THRESHOLD turns, targeting roughly one subagent
    per checkpoint, so it re-fires in a session that fanned out early and then
    ran on sequentially.

    Args:
        turn_count: The current turn count.
        agent_count: The number of subagent invocations recorded this session.

    Returns:
        True if an agent fan-out nudge should be shown.
    """
    if turn_count < _AGENT_NUDGE_THRESHOLD or turn_count % _AGENT_NUDGE_THRESHOLD != 0:
        return False
    return agent_count < turn_count // _AGENT_NUDGE_THRESHOLD


def reset(task_id: str) -> None:
    """Clear the turn count for a session.

    Args:
        task_id: The session or task identifier.
    """
    _store.reset(task_id)


_COMMIT_REMINDER = (
    "COMMIT REMINDER: There are a large number of uncommitted changes. "
    "SHOULD commit your work now to keep changes manageable."
)
_COMMIT_LINE_THRESHOLD = 200

_RETRO_THRESHOLD = 5
_RETRO_REMINDER = (
    "You have completed {count} sessions since your last /retrospective. "
    "SHOULD run it to capture learnings across recent sessions."
)

_LATE_NIGHT_START = 22
_EARLY_MORNING_END = 6
_INFO_REMINDER_CHANCE = 0.25
_SIDE_REQUEST_REMINDER_CHANCE = 0.15

_DISMISSAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bpre-?existing (error|issue|bug|failure|problem)",
        r"\b(error|issue|bug|failure|problem) (is|was) pre-?existing\b",
        r"\bnot (caused|related to|introduced) by (my|this) (change|fix|commit|edit)",
        r"\bunrelated to (my|this|the current) change\b",
        r"\bnot something (i|we) (need|have) to fix\b",
        r"\bout of scope for this (change|fix|task)\b",
    ]
]

_DISMISSAL_NUDGE = (
    "DISMISSED ISSUE DETECTED: You described a problem as pre-existing/unrelated instead of "
    "fixing it. Unless the user has explicitly told you not to, MUST log a follow-up now "
    "(a memory task/ entity or TODO) so it isn't lost."
)

_CORRECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\byou should\b",
        r"\bdon'?t\b",
        r"\bplease don'?t\b",
        r"\bstop\b",
        r"\bstop doing\b",
        r"\bfrom now on\b",
        r"\bin future\b",
        r"\bgoing forward\b",
        r"\bcorrection\b",
        r"\bwrong\b",
        r"\bthat'?s not\b",
        r"\bnot like that\b",
        r"\bwhy didn'?t you\b",
        r"\byou keep\b",
        r"\byou always\b",
        r"\byou never\b",
    ]
]

_INFO_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bactually\b",
        r"\bremember that\b",
        r"\balways\b",
        r"\bnever\b",
        r"\bprefer\b",
        r"\bi prefer\b",
        r"\bnote that\b",
        r"\bremember (to|this|that|how)\b",
    ]
]

_SCOPE_CHECK_REMINDER = (
    "SESSION LENGTH CHECK: This session has reached {turns} user turns. "
    "MUST pause and assess: is this still one coherent change, or has scope crept? "
    "Where multiple unrelated changes have accumulated, MUST commit what's done, note remaining work as TODOs, "
    "and suggest splitting into a new session."
)

# Update prompts/shared/rules/hooks.md if this correction reminder changes.
_CORRECTION_REMINDER = (
    "CORRECTION DETECTED: The user is correcting your behavior. "
    "MUST persist the correction to memory now, then ASK whether they want a rule or skill change for it."
)

_AGENT_NUDGE_REMINDER = (
    "FAN-OUT CHECK: {turns} turns in and subagent use is lagging behind this session's length. "
    "Where non-trivial work is left, MUST parallelise with subagents (research, independent edits, verification) "
    "rather than work sequentially."
)

_INFO_REMINDER = (
    "REMINDER: Has the user said anything that should be persisted?\n"
    "MUST check: new information, preferences, decisions -> persist to memory."
)

_SIDE_REQUEST_REMINDER = (
    "REMINDER: MUST scan recent turns for any side-request the user raised that hasn't been "
    "tracked yet (a task/ entity in memory + a checklist entry), per the todos rule. "
    "A prose acknowledgment ('I'll get to that after') does not count as tracked."
)

_LATE_EARLY_WARNING = "You're working late/early. MUST double-check before committing or making major changes."


def _parse_diff_stat_line(line: str) -> int:
    """Extract inserted+deleted line count from a single git diff --stat output line.

    Args:
        line: A single line from git diff --stat output.

    Returns:
        Total line count for this stat line.
    """
    total = 0
    for part in line.split(","):
        stripped = part.strip()
        if "insertion" in stripped or "deletion" in stripped:
            with contextlib.suppress(ValueError, IndexError):
                total += int(stripped.split()[0])
    return total


def _get_diff_line_count(workspace_roots: list[str]) -> int:
    """Return total added+removed lines in the working tree of the first valid repo.

    Args:
        workspace_roots: Workspace root paths to search for a git repo.

    Returns:
        Total diff line count, or 0 if no repo or no diff.
    """
    for root in workspace_roots:
        try:
            repo = git.Repo(root)
            diff = repo.git.diff("--stat", "HEAD")
        except (
            git.exc.InvalidGitRepositoryError,
            git.exc.GitCommandError,
            git.exc.NoSuchPathError,
        ):
            continue
        else:
            return sum(_parse_diff_stat_line(line) for line in diff.splitlines())
    return 0


def _contains_dismissal_signal(message: str) -> bool:
    """Check if the assistant's last message dismisses an issue instead of fixing it.

    Args:
        message: The assistant's last response text.

    Returns:
        True if the message matches any dismissal-signal pattern.
    """
    return any(pattern.search(message) for pattern in _DISMISSAL_PATTERNS)


def _contains_correction_signal(message: str) -> bool:
    """Check if a user message contains signals that the user is correcting behavior.

    Returns:
        True if the message matches any correction-signal pattern.
    """
    return any(pattern.search(message) for pattern in _CORRECTION_PATTERNS)


def _contains_info_signal(message: str) -> bool:
    """Check if a user message contains signals that new information should be persisted.

    Returns:
        True if the message matches any info-signal pattern.
    """
    return any(pattern.search(message) for pattern in _INFO_PATTERNS)


class NudgesPlugin(HooksPlugin):
    """Assorted reminders: commit size, retrospective, dismissals, and prompt nudges."""

    def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
        """Dispatch to the per-scope reminder builder.

        Args:
            hook_name: The hook event or plugin-scope name.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult carrying any reminders, or None.
        """
        if hook_name == CanonicalHook.POST_TOOL_USE:
            return self._post_tool_use(kwargs)
        if hook_name == CanonicalHook.STOP:
            return self._stop(kwargs)
        if hook_name == CanonicalHook.USER_PROMPT_SUBMIT:
            return self._user_prompt_submit(kwargs)
        if hook_name == CanonicalHook.TASK_START:
            task_id = kwargs.get("task_id")
            source = kwargs.get("source")
            if isinstance(task_id, str) and source not in NO_RESET_TASK_START_SOURCES:
                reset(task_id)
            return None
        if hook_name == CanonicalHook.TASK_COMPLETE:
            task_id = kwargs.get("task_id")
            if isinstance(task_id, str):
                reset(task_id)
            return None
        return None

    def _post_tool_use(self, kwargs: dict[str, object]) -> HookResult | None:
        """Build the commit-size and retrospective reminders for a tool call.

        Returns:
            A HookResult with any reminders, or None.
        """
        tool_name = kwargs.get("tool_name")
        task_id = kwargs.get("task_id")
        parameters = kwargs.get("parameters")
        workspace_roots = kwargs.get("workspace_roots")
        if not isinstance(tool_name, str) or not isinstance(task_id, str):
            return None
        notes: list[str] = []
        if tool_name in FILE_EDIT_TOOLS and isinstance(workspace_roots, list):
            diff_lines = _get_diff_line_count(workspace_roots)
            if diff_lines > _COMMIT_LINE_THRESHOLD:
                notes.append(f"{_COMMIT_REMINDER} ({diff_lines} lines changed)")
        if isinstance(parameters, dict) and is_wrap_up_skill(tool_name, parameters):
            count = record_session(task_id)
            if count is not None and count >= _RETRO_THRESHOLD:
                notes.append(_RETRO_REMINDER.format(count=count))
        return HookResult(notes=notes) if notes else None

    def _stop(self, kwargs: dict[str, object]) -> HookResult | None:
        """Build the dismissed-issue nudge from the assistant's last turn.

        Returns:
            A HookResult with the nudge, or None.
        """
        transcript_path = kwargs.get("transcript_path")
        if not isinstance(transcript_path, str):
            return None
        text = get_protocol().transcript.turn_assistant_text(transcript_path)
        if _contains_dismissal_signal(text):
            return HookResult(notes=[_DISMISSAL_NUDGE])
        return None

    def _user_prompt_submit(self, kwargs: dict[str, object]) -> HookResult | None:
        """Build the session-length, fan-out, timing, and signal reminders.

        Returns:
            A HookResult with any reminders, or None.
        """
        task_id = kwargs.get("task_id")
        message = kwargs.get("message")
        if not isinstance(task_id, str) or not isinstance(message, str):
            return None
        notes: list[str] = []
        turn_count = increment(task_id)
        if should_remind(turn_count):
            notes.append(_SCOPE_CHECK_REMINDER.format(turns=turn_count))
        if should_nudge_agents(turn_count, agent_use_count(task_id)):
            notes.append(_AGENT_NUDGE_REMINDER.format(turns=turn_count))
        hour = local_now().hour
        if hour >= _LATE_NIGHT_START or hour < _EARLY_MORNING_END:
            notes.append(_LATE_EARLY_WARNING)
        if _contains_correction_signal(message):
            notes.append(_CORRECTION_REMINDER)
        elif _contains_info_signal(message) or random.random() < _INFO_REMINDER_CHANCE:
            notes.append(_INFO_REMINDER)
        if random.random() < _SIDE_REQUEST_REMINDER_CHANCE:
            notes.append(_SIDE_REQUEST_REMINDER)
        return HookResult(notes=notes) if notes else None
