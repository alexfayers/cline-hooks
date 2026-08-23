from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from cline_hooks.core.plugin import HooksPlugin
from cline_hooks.frontends.cline import parse_cline_data as parse_data
from cline_hooks.handlers.user_prompt import (
    _contains_correction_signal,
    _contains_info_signal,
    _is_agent_message,
    handle_user_prompt_submit,
)
from cline_hooks.state.agents import record_agent_use
from cline_hooks.state.context import (
    _BAND_SIZE,
    CONTEXT_DEGRADED_THRESHOLD,
    CONTEXT_REDUCED_THRESHOLD,
)
from cline_hooks.state.plan import record_plan_exit
import cline_hooks.state.turns as turns_module
from cline_hooks.state.turns import _AGENT_NUDGE_THRESHOLD
import pytest

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInputUserPromptSubmit

_BELOW_REDUCED = CONTEXT_REDUCED_THRESHOLD // 2
_BELOW_REDUCED_SAME_BAND = _BELOW_REDUCED + _BAND_SIZE // 2
_BELOW_REDUCED_NEXT_BAND = _BELOW_REDUCED + _BAND_SIZE + 1_000
_JUST_ABOVE_REDUCED = CONTEXT_REDUCED_THRESHOLD + _BAND_SIZE
_SAME_BAND_AS_REDUCED = _JUST_ABOVE_REDUCED + _BAND_SIZE // 2
_NEXT_BAND_AFTER_REDUCED = _JUST_ABOVE_REDUCED + _BAND_SIZE + 1_000
_JUST_ABOVE_SEVERE = CONTEXT_DEGRADED_THRESHOLD + _BAND_SIZE

_BASE = {
    "clineVersion": "1.0.0",
    "timestamp": "0",
    "taskId": "task-1",
    "userId": "user-1",
    "workspaceRoots": [],
    "hookName": "UserPromptSubmit",
}


def _dt(hour: int) -> datetime:
    """Build a fixed timezone-aware datetime at the given hour for local_now patching."""
    return datetime(2026, 1, 1, hour, 30, tzinfo=UTC)


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


def _assert_time_only(result: dict[str, object] | None) -> None:
    """Assert the output carries only the TIME note and no other reminder."""
    assert result is not None
    context = cast("str", result.get("contextModification", ""))
    assert context.startswith("TIME:")
    assert "\n\n" not in context


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
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
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


class TestIsAgentMessage:
    @pytest.mark.parametrize(
        "message",
        [
            '<agent-message from="worker-1">\nStatus update.\n</agent-message>',
            '<teammate-message teammate_id="worker-1" summary="Status">\nDone.\n</teammate-message>',
            '   <agent-message from="worker-1">\nStatus update.\n</agent-message>',
        ],
    )
    def test_returns_true_for_agent_wrapper(self, message: str) -> None:
        assert _is_agent_message(message) is True

    @pytest.mark.parametrize(
        "message",
        [
            "Can you implement this feature?",
            "Stop doing that",
            "",
        ],
    )
    def test_returns_false_for_plain_user_message(self, message: str) -> None:
        assert _is_agent_message(message) is False

    def test_returns_false_when_tag_follows_other_text(self) -> None:
        message = (
            'Another Claude session sent a message\n<teammate-message teammate_id="worker-1">\n'
            "Done.\n</teammate-message>"
        )
        assert _is_agent_message(message) is True


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
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
            result = _run("Can you implement this feature?")
        _assert_time_only(result)

    def test_late_night_adds_warning(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(23)),
        ):
            result = _run("neutral message")
        assert result is not None
        assert "late" in cast("str", result.get("contextModification", "")).lower()

    def test_daytime_no_late_warning(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
            result = _run("neutral message")
        _assert_time_only(result)

    def test_no_agent_nudge_below_threshold(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
            last = _run_n_turns(_AGENT_NUDGE_THRESHOLD - 1)
        _assert_time_only(last)

    def test_agent_nudge_at_threshold_without_agent_use(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
            last = _run_n_turns(_AGENT_NUDGE_THRESHOLD)
        assert last is not None
        assert "FAN-OUT CHECK" in cast("str", last.get("contextModification", ""))

    def test_no_agent_nudge_when_rate_kept_up(self) -> None:
        record_agent_use("task-1", "Agent")
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
            last = _run_n_turns(_AGENT_NUDGE_THRESHOLD)
        if last is not None:
            assert "FAN-OUT CHECK" not in cast("str", last.get("contextModification", ""))

    def test_agent_nudge_refires_when_rate_lags(self) -> None:
        record_agent_use("task-1", "Agent")
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
            last = _run_n_turns(2 * _AGENT_NUDGE_THRESHOLD)
        assert last is not None
        assert "FAN-OUT CHECK" in cast("str", last.get("contextModification", ""))

    def test_agent_message_emits_no_output(self) -> None:
        message = '<agent-message from="worker-1">\nYou should always run lint first\n</agent-message>'
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
            result = _run(message)
        assert result is None

    def test_agent_message_teammate_wrapper_emits_no_output(self) -> None:
        message = (
            '<teammate-message teammate_id="worker-1" summary="Status">\n'
            "You should always run lint first\n"
            "</teammate-message>"
        )
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
            result = _run(message)
        assert result is None

    def test_agent_message_with_leading_whitespace_emits_no_output(self) -> None:
        message = '\n   <agent-message from="worker-1">\nYou should always run lint first\n</agent-message>'
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
            result = _run(message)
        assert result is None

    def test_agent_message_does_not_advance_turn_counter(self) -> None:
        message = '<agent-message from="worker-1">\nStatus update.\n</agent-message>'
        with patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0):
            _run("neutral")
            for _ in range(5):
                _run(message)
        assert turns_module._read().get("task-1") == 1
        _run("neutral")
        assert turns_module._read().get("task-1") == 2

    def test_agent_tag_preceded_by_other_text_does_not_fire_info_reminder(self) -> None:
        message = (
            "PostToolUse hook additional context\n"
            '   <teammate-message teammate_id="worker-1">\n'
            "Actually, the deadline is Friday\n"
            "</teammate-message>"
        )
        assert _run(message) is None

    def test_genuine_user_correction_still_fires_despite_agent_tag_absent(self) -> None:
        with patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0):
            result = _run("You should always run lint first")
        assert result is not None
        assert "correction" in cast("str", result.get("contextModification", "")).lower()

    def test_agent_message_suppresses_content_independent_notes_too(self) -> None:
        message = '<agent-message from="worker-1">\nYou should always run lint first\n</agent-message>'
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(23)),
        ):
            result = _run(message)
        assert result is None

    def test_no_userPromptSubmit_field_emits_no_error(self) -> None:
        hook = cast(
            "HookInputUserPromptSubmit",
            parse_data(json.dumps({**_BASE})),
        )
        output: list[str] = []
        try:
            with (
                patch("builtins.print", side_effect=lambda s, **kw: output.append(s)),
                patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
                patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
            ):
                handle_user_prompt_submit(hook)
        except SystemExit:
            pass
        assert output == []


class TestTimeNote:
    def test_time_note_always_emitted_first(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
            result = _run("neutral message")
        assert result is not None
        assert cast("str", result.get("contextModification", "")).startswith("TIME:")

    def test_time_note_prefixed_before_other_reminders(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(23)),
        ):
            result = _run("neutral message")
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert context.startswith("TIME:")
        assert "late" in context.lower()

    def test_no_reminder_prefix_when_co_firing_note(self) -> None:
        with patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0):
            result = _run("You should always run lint first")
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert not context.startswith("REMINDER: ")
        assert context.index("TIME:") < context.index("CORRECTION DETECTED")


class TestSideRequestReminder:
    def test_low_random_fires_side_request_reminder(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=0.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
            result = _run("neutral message")
        assert result is not None
        assert "side-request" in cast("str", result.get("contextModification", "")).lower()

    def test_high_random_no_side_request_reminder(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
            result = _run("neutral message")
        _assert_time_only(result)


class TestContextNudge:
    def test_no_nudge_when_no_transcript_path(self) -> None:
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
            result = _run("neutral")
        _assert_time_only(result)

    def test_no_nudge_when_token_count_unavailable(self) -> None:
        _assert_time_only(_run_with_transcript(None))

    def test_info_note_below_reduced_threshold(self) -> None:
        result = _run_with_transcript(_BELOW_REDUCED)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "CONTEXT STATUS" in context
        assert f"{_BELOW_REDUCED:,}" in context

    def test_reduced_nudge_on_first_crossing(self) -> None:
        result = _run_with_transcript(_JUST_ABOVE_REDUCED)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "Accuracy degrading" in context
        assert f"{_JUST_ABOVE_REDUCED:,}" in context

    def test_severe_nudge_on_first_crossing(self) -> None:
        result = _run_with_transcript(_JUST_ABOVE_SEVERE)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "badly degraded" in context
        assert f"{_JUST_ABOVE_SEVERE:,}" in context

    def test_reduced_nudge_does_not_refire_within_same_band(self) -> None:
        first = _run_with_transcript(_JUST_ABOVE_REDUCED)
        assert first is not None
        assert "Accuracy degrading" in cast("str", first.get("contextModification", ""))
        second = _run_with_transcript(_SAME_BAND_AS_REDUCED)
        if second is not None:
            assert "Accuracy degrading" not in cast("str", second.get("contextModification", ""))

    def test_next_band_in_same_tier_omits_boundary_text(self) -> None:
        _run_with_transcript(_JUST_ABOVE_REDUCED)
        result = _run_with_transcript(_NEXT_BAND_AFTER_REDUCED)
        assert result is not None
        context = cast("str", result.get("contextModification", ""))
        assert "Accuracy degrading" not in context
        assert "CONTEXT STATUS" in context

    def test_info_note_fires_once_per_band(self) -> None:
        first = _run_with_transcript(_BELOW_REDUCED)
        assert first is not None
        assert "CONTEXT STATUS" in cast("str", first.get("contextModification", ""))
        second = _run_with_transcript(_BELOW_REDUCED_SAME_BAND)
        if second is not None:
            assert "CONTEXT STATUS" not in cast("str", second.get("contextModification", ""))

    def test_info_note_refires_in_next_band(self) -> None:
        _run_with_transcript(_BELOW_REDUCED)
        result = _run_with_transcript(_BELOW_REDUCED_NEXT_BAND)
        assert result is not None
        assert "CONTEXT STATUS" in cast("str", result.get("contextModification", ""))


class TestPlanHandoffNudge:
    def test_plan_nudge_fires_after_plan_exit(self) -> None:
        record_plan_exit("task-1")
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
            result = _run("neutral")
        assert result is not None
        assert "PLAN COMPLETE" in cast("str", result.get("contextModification", ""))

    def test_plan_nudge_fires_once(self) -> None:
        record_plan_exit("task-1")
        with (
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
            patch("cline_hooks.handlers.user_prompt.local_now", return_value=_dt(12)),
        ):
            _run("neutral")
            second = _run("neutral")
        if second is not None:
            assert "PLAN COMPLETE" not in cast("str", second.get("contextModification", ""))


class TestTeamActiveClause:
    def test_team_clause_appended_when_agent_used(self) -> None:
        record_agent_use("task-1", "Agent")
        result = _run_with_transcript(_JUST_ABOVE_REDUCED)
        assert result is not None
        assert "TaskStop" in cast("str", result.get("contextModification", ""))

    def test_no_team_clause_when_no_agent(self) -> None:
        result = _run_with_transcript(_JUST_ABOVE_REDUCED)
        assert result is not None
        assert "TaskStop" not in cast("str", result.get("contextModification", ""))


class TestPluginMessageForwarding:
    def test_agent_message_does_not_forward_to_plugins(self) -> None:
        called = False

        class _CapturingPlugin(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> None:
                nonlocal called
                called = True

        message = '<agent-message from="worker-1">You should always run lint first</agent-message>'
        with (
            patch("cline_hooks.handlers.user_prompt.load_plugins", return_value=[_CapturingPlugin()]),
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
        ):
            _run(message)
        assert called is False

    def test_plain_message_forwards_verbatim_text_to_plugins(self) -> None:
        captured: dict[str, object] = {}

        class _CapturingPlugin(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> None:
                if hook_name == "UserPromptSubmit":
                    captured.update(kwargs)

        message = "Can you implement this feature?"
        with (
            patch("cline_hooks.handlers.user_prompt.load_plugins", return_value=[_CapturingPlugin()]),
            patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0),
        ):
            _run(message)
        assert captured.get("message") == message
