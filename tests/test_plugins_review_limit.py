from __future__ import annotations

import logging
import re
import subprocess
from typing import TYPE_CHECKING

import pytest

from cline_hooks.config import set_max_in_flight_reviews
from cline_hooks.core.plugin import HooksPlugin, hookimpl
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool, PluginScope
from cline_hooks.plugins.review_limit import ReviewLimitPlugin, ReviewSource, drop_reviews, in_flight_reviews
from tests.conftest import UNSUPPORTED_SYNTAX

if TYPE_CHECKING:
    from collections.abc import Callable
    from unittest.mock import MagicMock

    from pytest_mock import MockerFixture

    from cline_hooks.core.plugin import HookResult


def _pr_url(number: int) -> str:
    return f"https://github.com/acme/widgets/pull/{number}"


def _guard(command: str) -> HookResult | None:
    return ReviewLimitPlugin().on_hook(PluginScope.PRE_SHELL, logger=logging.getLogger("test"), command=command)


def _ran(command: str, output: str) -> None:
    ReviewLimitPlugin().on_hook(
        CanonicalHook.POST_TOOL_USE,
        logger=logging.getLogger("test"),
        tool_name=CanonicalTool.SHELL,
        parameters={"command": command},
        success=True,
        tool_result=output,
    )


def _open_prs(count: int) -> None:
    for number in range(1, count + 1):
        _ran("gh pr create --fill", f"Creating pull request\n{_pr_url(number)}\n")


@pytest.fixture
def gh_state(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "cline_hooks.plugins.review_limit.subprocess.run", return_value=mocker.Mock(returncode=0, stdout="open\n")
    )


def test_blocks_a_new_pr_at_the_limit_and_says_how_to_fix_it(gh_state: MagicMock) -> None:
    _open_prs(5)
    result = _guard("gh pr create --fill")
    assert result is not None
    block = str(result.block)
    assert "5 reviews are in flight" in block
    assert "limit of 5" in block
    assert "max_in_flight_reviews" in block
    assert "cline-hook reviews --drop" in block
    assert _pr_url(5) in block


def test_allows_a_new_pr_under_the_limit(gh_state: MagicMock) -> None:
    _open_prs(4)
    assert _guard("gh pr create --fill") is None
    gh_state.assert_not_called()


@pytest.mark.parametrize(
    "command", ["gh pr edit 5 --title x", "gh pr comment 5 -b hi", "git push", "gh pr view 5", "gh pr create-ish"]
)
def test_allows_updates_and_other_commands_at_the_limit(gh_state: MagicMock, command: str) -> None:
    _open_prs(5)
    assert _guard(command) is None


def test_a_raised_limit_applies_to_the_next_check(gh_state: MagicMock) -> None:
    _open_prs(5)
    assert _guard("gh pr create --fill") is not None
    set_max_in_flight_reviews(6)
    assert _guard("gh pr create --fill") is None


def test_prunes_closed_prs_at_the_limit(gh_state: MagicMock, mocker: MockerFixture) -> None:
    _open_prs(5)
    gh_state.side_effect = lambda args, **_: mocker.Mock(
        returncode=0, stdout="closed" if args[4].endswith("pulls/2") else "open"
    )
    assert _guard("gh -R acme/widgets pr create --fill") is None
    assert _pr_url(2) not in in_flight_reviews()
    assert gh_state.call_args.args[0][:5] == ["gh", "api", "--hostname", "github.com", "repos/acme/widgets/pulls/5"]


@pytest.mark.parametrize("failure", [OSError("offline"), subprocess.TimeoutExpired("gh", 10)])
def test_keeps_prs_whose_state_cannot_be_checked(gh_state: MagicMock, failure: Exception) -> None:
    _open_prs(5)
    gh_state.side_effect = failure
    assert _guard("gh pr create --fill") is not None
    assert len(in_flight_reviews()) == 5


def test_records_only_the_output_of_a_successful_create(gh_state: MagicMock) -> None:
    _ran("gh pr view 9", _pr_url(9))
    ReviewLimitPlugin().on_hook(
        CanonicalHook.POST_TOOL_USE,
        logger=logging.getLogger("test"),
        tool_name=CanonicalTool.SHELL,
        parameters={"command": "gh pr create"},
        success=False,
        tool_result=_pr_url(8),
    )
    assert in_flight_reviews() == {}


def test_dropped_reviews_free_their_slots(gh_state: MagicMock) -> None:
    _open_prs(5)
    drop_reviews([_pr_url(1)])
    assert _guard("gh pr create --fill") is None
    gh_state.assert_not_called()


def test_a_contributed_source_is_guarded(use_plugins: Callable[..., None]) -> None:
    class CustomSourcePlugin(HooksPlugin):
        @hookimpl
        def review_sources(self) -> list[ReviewSource]:
            return [
                ReviewSource(name="custom", creates=lambda cmd: cmd.name == "review", review_id=re.compile(r"R-\d+"))
            ]

    use_plugins(ReviewLimitPlugin(), CustomSourcePlugin())
    set_max_in_flight_reviews(1)
    _ran("review", "Created R-1")
    assert in_flight_reviews() == {"R-1": "custom"}
    assert _guard("review") is not None


@pytest.mark.parametrize("command", ["", "  ", *UNSUPPORTED_SYNTAX])
def test_ignores_blank_and_unparseable_commands(gh_state: MagicMock, command: str) -> None:
    _open_prs(5)
    _ran(command, _pr_url(9))
    assert _guard(command) is None
    assert len(in_flight_reviews()) == 5
