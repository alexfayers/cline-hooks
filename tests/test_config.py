from __future__ import annotations

import contextvars
import json
from typing import TYPE_CHECKING

import pytest

from cline_hooks.config import agent_teams_enabled, get_push_block_markers, hook_env, set_hook_env

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from pytest_mock import MockerFixture


class TestAgentTeamsEnabled:
    def test_defaults_to_false_when_unset(self, mocker: MockerFixture) -> None:
        mocker.patch.dict("os.environ", {}, clear=True)
        assert agent_teams_enabled() is False

    def test_true_when_env_var_set(self, mocker: MockerFixture) -> None:
        mocker.patch.dict("os.environ", {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"})
        assert agent_teams_enabled() is True

    def test_true_for_falsy_looking_string_value(self, mocker: MockerFixture) -> None:
        mocker.patch.dict("os.environ", {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "false"})
        assert agent_teams_enabled() is True

    def test_false_when_set_to_empty_string(self, mocker: MockerFixture) -> None:
        mocker.patch.dict("os.environ", {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": ""})
        assert agent_teams_enabled() is False

    def test_true_from_config_file_when_env_unset(self, mocker: MockerFixture, tmp_path: Path) -> None:
        mocker.patch.dict("os.environ", {}, clear=True)
        (tmp_path / "config.json").write_text(json.dumps({"agent_teams_enabled": True}))
        assert agent_teams_enabled() is True

    def test_env_var_present_wins_over_config_file(self, mocker: MockerFixture, tmp_path: Path) -> None:
        mocker.patch.dict("os.environ", {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": ""})
        (tmp_path / "config.json").write_text(json.dumps({"agent_teams_enabled": True}))
        assert agent_teams_enabled() is False

    def test_false_when_config_file_unparseable(self, mocker: MockerFixture, tmp_path: Path) -> None:
        mocker.patch.dict("os.environ", {}, clear=True)
        (tmp_path / "config.json").write_text("not json")
        assert agent_teams_enabled() is False


class TestGetPushBlockMarkers:
    def test_defaults_to_empty(self, mocker: MockerFixture) -> None:
        mocker.patch.dict("os.environ", {}, clear=True)
        assert get_push_block_markers() == ()

    def test_parses_comma_separated_values(self, mocker: MockerFixture) -> None:
        mocker.patch.dict("os.environ", {"CLINE_HOOKS_PUSH_BLOCK_MARKERS": "foo,bar"})
        assert get_push_block_markers() == ("foo", "bar")

    def test_strips_whitespace_and_drops_empty_entries(self, mocker: MockerFixture) -> None:
        mocker.patch.dict("os.environ", {"CLINE_HOOKS_PUSH_BLOCK_MARKERS": " foo , , bar "})
        assert get_push_block_markers() == ("foo", "bar")

    def test_uses_config_file_list_when_env_unset(self, mocker: MockerFixture, tmp_path: Path) -> None:
        mocker.patch.dict("os.environ", {}, clear=True)
        (tmp_path / "config.json").write_text(json.dumps({"push_block_markers": ["foo", " bar "]}))
        assert get_push_block_markers() == ("foo", "bar")

    def test_env_var_present_wins_over_config_file(self, mocker: MockerFixture, tmp_path: Path) -> None:
        mocker.patch.dict("os.environ", {"CLINE_HOOKS_PUSH_BLOCK_MARKERS": "baz"})
        (tmp_path / "config.json").write_text(json.dumps({"push_block_markers": ["foo"]}))
        assert get_push_block_markers() == ("baz",)

    def test_ignores_non_list_config_value(self, mocker: MockerFixture, tmp_path: Path) -> None:
        mocker.patch.dict("os.environ", {}, clear=True)
        (tmp_path / "config.json").write_text(json.dumps({"push_block_markers": "not-a-list"}))
        assert get_push_block_markers() == ()


def _in_hook_env[T](env: Mapping[str, str], func: Callable[[], T]) -> T:
    def run() -> T:
        set_hook_env(env)
        return func()

    return contextvars.copy_context().run(run)


class TestHookEnv:
    def test_defaults_to_the_process_environ(self, mocker: MockerFixture) -> None:
        mocker.patch.dict("os.environ", {"CLINE_HOOKS_TEST_ENV": "1"})
        assert hook_env()["CLINE_HOOKS_TEST_ENV"] == "1"

    @pytest.mark.parametrize(
        ("var", "reader", "expected"),
        [
            ("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", agent_teams_enabled, True),
            ("CLINE_HOOKS_PUSH_BLOCK_MARKERS", get_push_block_markers, ("foo",)),
        ],
    )
    def test_readers_use_the_hook_env_over_the_process_env(
        self,
        mocker: MockerFixture,
        var: str,
        reader: Callable[[], bool | tuple[str, ...]],
        expected: bool | tuple[str, ...],
    ) -> None:
        mocker.patch.dict("os.environ", {var: ""})
        assert _in_hook_env({var: "foo"}, reader) == expected
