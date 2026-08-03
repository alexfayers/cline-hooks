from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest

from cline_hooks.frontends.cline import parse_cline_data as parse_data
from cline_hooks.handlers.user_prompt import (
    _contains_correction_signal,
    _contains_info_signal,
    handle_user_prompt_submit,
)
from cline_hooks.state.agents import record_agent_use
from cline_hooks.state.plan import record_plan_exit
from cline_hooks.state.turns import _AGENT_NUDGE_THRESHOLD

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputUserPromptSubmit

_BASE = {
    "clineVersion": "1.0.0",
    "timestamp": "0",
    "taskId": "task-1",
    "userId": "user-1",
    "workspaceRoots": [],
    "hookName": "UserPromptSubmit",
}


def _make_hook(user_message: str = "") -> HookInputUserPromptSubmit:
    return cast(
        "HookInputUserPromptSubmit",
        parse_data(
            json.dumps({
                **_BASE,
                "userPromptSubmit": {"userMessage": user_message},
            })
        ),
    )


def _run(user_message: str = "") -> dict[str, object] | None:
    hook = _make_hook(user_message)
    output: list[str] = []
    try:
        with patch("builtins.print", side_effect=lambda s, **kw: output.append(s)):
            handle_user_prompt_submit(hook)
    except SystemExit:
        pass
    if not output:
        return None
    return cast("dict[str, object]", json.loads(output[0]))


def _run_n_turns(n: int) -> dict[str, object] | None:
    """Submit n neutral prompts and return the output from the last turn."""
    last: dict[str, object] | None = None
    for _ in range(n):
        last = _run("neutral")
    return last


def _run_with_transcript(token_count: int | None) -> dict[str, object] | None:
    """Run a neutral prompt with a transcript path, faking the reported token count."""
    hook = cast(
        "HookInputUserPromptSubmit",
        parse_data(
            json.dumps({
                **_BASE,
                "userPromptSubmit": {"userMessage": "neutral"},
                "transcriptPath": "session.jsonl",
            })
        ),
    )
    output: list[str] = []
    try:
        with (
            patch("builtins.print", side_effect=lambda s, _out=output, **kw: _out.append(s)),
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.get_context_tokens", return_value=token_count),
            patch("cline_hooks.handlers.user_prompt.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.hour = 12
            handle_user_prompt_submit(hook)
    except SystemExit:
        pass
    if not output:
        return None
    return cast("dict[str, object]", json.loads(output[0]))


class TestContainsCorrectionSignal:
    @pytest.mark.parametrize(
        "message",
        [
            "You should always use type hints",
            "Don't add comments explaining changes",
            "Please don't use emdash characters",
            "From now on, use British English",
            "Going forward, always run just before committing",
            "In future, check for tests before committing",
            "Correction: the method is called parse_data",
            "That's not the right approach",
            "Stop doing that",
            "Why didn't you check the tests first?",
            "You keep making the same mistake",
            "You always forget to run lint",
            "You never persist things properly",
            "Not like that, do it differently",
            "Wrong, it should be the other way",
        ],
    )
    def test_returns_true_for_correction_signal(self, message: str) -> None:
        assert _contains_correction_signal(message) is True

    @pytest.mark.parametrize(
        "message",
        [
            "Can you implement this feature?",
            "What does this function do?",
            "Run the tests please",
            "Create a new file",
            "Actually, the API returns JSON",
            "Remember that the deadline is Friday",
            "",
        ],
    )
    def test_returns_false_for_non_correction(self, message: str) -> None:
        assert _contains_correction_signal(message) is False

    def test_case_insensitive(self) -> None:
        assert _contains_correction_signal("STOP doing that") is True
        assert _contains_correction_signal("YOU SHOULD check first") is True


class TestContainsInfoSignal:
    @pytest.mark.parametrize(
        "message",
        [
            "Actually, the API returns JSON",
            "Remember that we prefer Google docstrings",
            "Never use the -f flag with rm",
            "I prefer minimal comments in code",
            "Note that this file uses camelCase",
            "Always run tests before pushing",
        ],
    )
    def test_returns_true_for_info_signal(self, message: str) -> None:
        assert _contains_info_signal(message) is True

    @pytest.mark.parametrize(
        "message",
        [
            "Can you implement this feature?",
            "What does this function do?",
            "Run the tests please",
            "Create a new file",
            "",
        ],
    )
    def test_returns_false_for_neutral_message(self, message: str) -> None:
        assert _contains_info_signal(message) is False

    def test_case_insensitive(self) -> None:
        assert _contains_info_signal("ALWAYS use type hints") is True
        assert _contains_info_signal("NEVER skip tests") is True


class TestHandleUserPromptSubmit:
    def test_correction_signal_fires_correction_reminder(self) -> None:
        with patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0):
            result = _run("You should always run lint first")
        assert result is not None
        assert "correction" in cast("str", result.get("contextModification", "")).lower()

    def test_correction_takes_priority_over_info(self) -> None:
        with patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0):
            result = _run("You should always use type hints")
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "correction" in context.lower()
        assert "persist to memory" not in context.lower()

    def test_info_signal_fires_info_reminder(self) -> None:
        with patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0):
            result = _run("Actually, the deadline is Friday")
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "persist to memory" in context.lower()

    def test_neutral_message_with_low_random_fires_info_reminder(self) -> None:
        with patch("cline_hooks.handlers.user_prompt.random.random", return_value=0.0):
            result = _run("Can you implement this feature?")
        assert result is not None
        assert "persist to memory" in cast("str", result.get("contextModification", "")).lower()

    def test_neutral_message_with_high_random_no_reminder(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.hour = 12
            result = _run("Can you implement this feature?")
        assert result is None

    def test_late_night_adds_warning(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.hour = 23
            result = _run("neutral message")
        assert result is not None
        assert "late" in cast("str", result.get("contextModification", "")).lower()

    def test_daytime_no_late_warning(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.hour = 12
            result = _run("neutral message")
        assert result is None

    def test_no_agent_nudge_below_threshold(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.hour = 12
            last = _run_n_turns(_AGENT_NUDGE_THRESHOLD - 1)
        assert last is None

    def test_agent_nudge_at_threshold_without_agent_use(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.hour = 12
            last = _run_n_turns(_AGENT_NUDGE_THRESHOLD)
        assert last is not None
        assert "FAN-OUT CHECK" in cast("str", last.get("contextModification", ""))

    def test_no_agent_nudge_when_rate_kept_up(self) -> None:
        record_agent_use("task-1", "Agent")
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.hour = 12
            last = _run_n_turns(_AGENT_NUDGE_THRESHOLD)
        if last is not None:
            assert "FAN-OUT CHECK" not in cast("str", last.get("contextModification", ""))

    def test_agent_nudge_refires_when_rate_lags(self) -> None:
        record_agent_use("task-1", "Agent")
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.hour = 12
            last = _run_n_turns(2 * _AGENT_NUDGE_THRESHOLD)
        assert last is not None
        assert "FAN-OUT CHECK" in cast("str", last.get("contextModification", ""))

    def test_no_userPromptSubmit_field_emits_no_error(self) -> None:
        hook = cast(
            "HookInputUserPromptSubmit",
            parse_data(json.dumps({**_BASE})),
        )
        output: list[str] = []
        with (
            patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.hour = 12
            handle_user_prompt_submit(hook)
        assert not output


class TestSideRequestReminder:
    def test_low_random_fires_side_request_reminder(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=0.0),
            patch("cline_hooks.handlers.user_prompt.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.hour = 12
            result = _run("neutral message")
        assert result is not None
        assert "side-request" in cast("str", result.get("contextModification", "")).lower()

    def test_high_random_no_side_request_reminder(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.hour = 12
            result = _run("neutral message")
        assert result is None


class TestContextNudge:
    def test_no_nudge_when_no_transcript_path(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.hour = 12
            result = _run("neutral")
        assert result is None

    def test_no_nudge_when_token_count_unavailable(self) -> None:
        assert _run_with_transcript(None) is None

    def test_info_note_below_reduced_threshold(self) -> None:
        result = _run_with_transcript(150_000)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "CONTEXT STATUS" in context
        assert "150,000" in context

    def test_reduced_nudge_on_first_crossing(self) -> None:
        result = _run_with_transcript(210_000)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "Accuracy degrading" in context
        assert "210,000" in context

    def test_severe_nudge_on_first_crossing(self) -> None:
        result = _run_with_transcript(410_000)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "badly degraded" in context
        assert "410,000" in context

    def test_reduced_nudge_does_not_refire_within_same_band(self) -> None:
        first = _run_with_transcript(210_000)
        assert first is not None
        assert "Accuracy degrading" in cast("str", first.get("contextModification", ""))
        second = _run_with_transcript(215_000)
        if second is not None:
            assert "Accuracy degrading" not in cast("str", second.get("contextModification", ""))

    def test_next_band_in_same_tier_omits_boundary_text(self) -> None:
        _run_with_transcript(210_000)
        result = _run_with_transcript(221_000)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "Accuracy degrading" not in context
        assert "CONTEXT STATUS" in context

    def test_info_note_fires_once_per_band(self) -> None:
        first = _run_with_transcript(150_000)
        assert first is not None
        assert "CONTEXT STATUS" in cast("str", first.get("contextModification", ""))
        second = _run_with_transcript(155_000)
        if second is not None:
            assert "CONTEXT STATUS" not in cast("str", second.get("contextModification", ""))

    def test_info_note_refires_in_next_band(self) -> None:
        _run_with_transcript(150_000)
        result = _run_with_transcript(161_000)
        assert result is not None
        assert "CONTEXT STATUS" in cast("str", result.get("contextModification", ""))


class TestPlanHandoffNudge:
    def test_plan_nudge_fires_after_plan_exit(self) -> None:
        record_plan_exit("task-1")
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.hour = 12
            result = _run("neutral")
        assert result is not None
        assert "PLAN COMPLETE" in cast("str", result.get("contextModification", ""))

    def test_plan_nudge_fires_once(self) -> None:
        record_plan_exit("task-1")
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.hour = 12
            _run("neutral")
            second = _run("neutral")
        if second is not None:
            assert "PLAN COMPLETE" not in cast("str", second.get("contextModification", ""))


class TestTeamActiveClause:
    def test_team_clause_appended_when_agent_used(self) -> None:
        record_agent_use("task-1", "Agent")
        result = _run_with_transcript(210_000)
        assert result is not None
        assert "TaskStop" in cast("str", result.get("contextModification", ""))

    def test_no_team_clause_when_no_agent(self) -> None:
        result = _run_with_transcript(210_000)
        assert result is not None
        assert "TaskStop" not in cast("str", result.get("contextModification", ""))
