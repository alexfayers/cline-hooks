from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import pytest

from cline_hooks.frontends.cline import parse_cline_data as parse_data
from cline_hooks.handlers.user_prompt import (
    _contains_persist_signal,
    handle_user_prompt_submit,
)

if TYPE_CHECKING:
    from cline_hooks.models import HookInputUserPromptSubmit

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


class TestContainsPersistSignal:
    @pytest.mark.parametrize(
        "message",
        [
            "Actually, you should use ruff instead",
            "You should always use type hints",
            "Remember that we prefer Google docstrings",
            "Never use the -f flag with rm",
            "Don't add comments explaining changes",
            "Please don't use emdash characters",
            "I prefer minimal comments in code",
            "From now on, use British English",
            "Going forward, always run just before committing",
            "In future, check for tests before committing",
            "Correction: the method is called parse_data",
            "That's not the right approach",
            "Note that this file uses camelCase",
            "Stop doing that",
        ],
    )
    def test_returns_true_for_persist_signal(self, message: str) -> None:
        assert _contains_persist_signal(message) is True

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
        assert _contains_persist_signal(message) is False

    def test_case_insensitive(self) -> None:
        assert _contains_persist_signal("ALWAYS use type hints") is True
        assert _contains_persist_signal("NEVER skip tests") is True


class TestHandleUserPromptSubmit:
    def test_persist_signal_message_always_fires_reminder(self) -> None:
        with patch("cline_hooks.handlers.user_prompt.random.random", return_value=1.0):
            result = _run("Actually, you should use ruff")
        assert result is not None
        assert "persisted" in cast("str", result.get("contextModification", "")).lower()

    def test_neutral_message_with_low_random_fires_reminder(self) -> None:
        with patch("cline_hooks.handlers.user_prompt.random.random", return_value=0.0):
            result = _run("Can you implement this feature?")
        assert result is not None
        assert "persisted" in cast("str", result.get("contextModification", "")).lower()

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
