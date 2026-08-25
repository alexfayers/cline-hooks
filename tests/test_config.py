from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cline_hooks.config import get_push_block_markers, is_frustration_detector_disabled

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


class TestIsFrustrationDetectorDisabled:
    def test_defaults_to_enabled(self, mocker: MockerFixture) -> None:
        mocker.patch.dict("os.environ", {}, clear=True)
        assert is_frustration_detector_disabled() is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "True", "yes", "YES", "Yes"])
    def test_truthy_values_disable(self, mocker: MockerFixture, value: str) -> None:
        mocker.patch.dict("os.environ", {"CLINE_HOOKS_DISABLE_FRUSTRATION_DETECTOR": value})
        assert is_frustration_detector_disabled() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "", "nope"])
    def test_falsy_values_keep_enabled(self, mocker: MockerFixture, value: str) -> None:
        mocker.patch.dict("os.environ", {"CLINE_HOOKS_DISABLE_FRUSTRATION_DETECTOR": value})
        assert is_frustration_detector_disabled() is False
