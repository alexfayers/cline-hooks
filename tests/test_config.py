from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.config import get_push_block_markers

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


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
