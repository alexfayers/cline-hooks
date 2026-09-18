from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.config import agent_teams_enabled, get_push_block_markers

if TYPE_CHECKING:
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
