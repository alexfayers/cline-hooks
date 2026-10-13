from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from cline_hooks.core.plugin import HooksPlugin, collect_hook_results, hookimpl, load_plugins
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.vocabulary import NO_RESET_TASK_START_SOURCES
from cline_hooks.plugins.startup_blocks import (
    NOTE_SEPARATOR,
    RESERVE_CHARS,
    StartupBlock,
    StartupBlocksPlugin,
    block_text,
)
from cline_hooks.state.skills import is_skill_called

if TYPE_CHECKING:
    from collections.abc import Callable

    from pytest_mock import MockerFixture


def contributor(*blocks: object) -> HooksPlugin:
    class Contributor(HooksPlugin):
        @hookimpl
        def startup_blocks(self, workspace_roots: list[str]) -> list[object]:
            return list(blocks)

    return Contributor()


def block(
    title: str = "alpha", body: str | Callable[[int | None], str] = "ALPHA BODY", **kwargs: object
) -> StartupBlock:
    return StartupBlock(
        title=title,
        replaces=f"do {title}",
        body=(lambda _: body) if isinstance(body, str) else body,
        **kwargs,  # type: ignore[arg-type]
    )


def cap_budget(mocker: MockerFixture, budget: int | None) -> None:
    protocol = type(get_protocol())
    assert protocol.frontend_spec is not None
    cap = None if budget is None else budget + RESERVE_CHARS
    mocker.patch.object(protocol, "frontend_spec", replace(protocol.frontend_spec, max_context_chars=cap))


def fallback(title: str) -> str:
    return f"{title} was not injected. Do this yourself: do {title}."


def run(source: str = "startup", **kwargs: object) -> list[str]:
    return collect_hook_results(
        load_plugins(), "TaskStart", task_id="task-1", workspace_roots=["/ws"], source=source, **kwargs
    ).notes


class TestEmission:
    def test_a_fresh_start_emits_a_header_what_the_block_replaces_and_the_body(
        self, use_plugins: Callable[..., None]
    ) -> None:
        use_plugins(StartupBlocksPlugin(), contributor(block()))

        assert run() == ["Startup block: alpha\nResult of: do alpha. Already done - do not repeat it.\n\nALPHA BODY"]

    def test_blocks_come_out_sorted_by_order_then_title(self, use_plugins: Callable[..., None]) -> None:
        use_plugins(
            StartupBlocksPlugin(),
            contributor(block("beta"), block("zeta", order=1)),
            contributor(block("alpha")),
        )

        titles = [note.splitlines()[0] for note in run()]

        assert titles == [f"Startup block: {title}" for title in ("zeta", "alpha", "beta")]

    def test_a_subagent_gets_no_block(self, use_plugins: Callable[..., None]) -> None:
        use_plugins(StartupBlocksPlugin(), contributor(block()))

        assert run(agent_id="sub-1") == []

    @pytest.mark.parametrize("source", sorted(NO_RESET_TASK_START_SOURCES))
    def test_a_resume_or_compact_gets_no_block(self, use_plugins: Callable[..., None], source: str) -> None:
        use_plugins(StartupBlocksPlugin(), contributor(block()))

        assert run(source) == []


class TestFallback:
    def test_a_raising_body_becomes_a_fallback_note(
        self, use_plugins: Callable[..., None], caplog: pytest.LogCaptureFixture
    ) -> None:
        broken = block("alpha", Mock(side_effect=RuntimeError("boom")))
        use_plugins(StartupBlocksPlugin(), contributor(broken))

        notes = run()

        assert notes == [fallback("alpha")]
        assert "boom" in caplog.text

    def test_a_non_block_item_is_dropped_and_logged(
        self, use_plugins: Callable[..., None], caplog: pytest.LogCaptureFixture
    ) -> None:
        use_plugins(StartupBlocksPlugin(), contributor("not a block", block()))

        assert run() == [block_text(block(), "ALPHA BODY")]
        assert "str" in caplog.text

    def test_a_skill_is_recorded_only_for_an_injected_block(
        self, use_plugins: Callable[..., None], mocker: MockerFixture
    ) -> None:
        cap_budget(mocker, 200)
        use_plugins(
            StartupBlocksPlugin(),
            contributor(block("alpha", "A", skill="alpha-skill"), block("beta", "B" * 1000, skill="beta-skill")),
        )

        run()

        assert is_skill_called("task-1", "alpha-skill")
        assert not is_skill_called("task-1", "beta-skill")


class TestBudget:
    def test_blocks_fit_then_overflow_to_fallback_notes_then_are_dropped_within_budget(
        self, use_plugins: Callable[..., None], mocker: MockerFixture, caplog: pytest.LogCaptureFixture
    ) -> None:
        cap_budget(mocker, 400)
        fits, measured = block("a-fits", "A" * 50), block("b-measured", Mock(return_value="B"))
        overflowing = [block(f"c-{index:02}", "X" * 1000) for index in range(50)]
        use_plugins(StartupBlocksPlugin(), contributor(fits, measured, *overflowing))

        notes = run()

        used = len(block_text(fits, "A" * 50)) + len(NOTE_SEPARATOR)
        measured.body.assert_called_once_with(400 - used - len(block_text(measured, "")))  # type: ignore[attr-defined]
        assert notes[:2] == [block_text(fits, "A" * 50), block_text(measured, "B")]
        assert notes[2:] == [fallback(b.title) for b in overflowing[: len(notes) - 2]]
        assert 2 < len(notes) < len(overflowing) + 2
        assert len(NOTE_SEPARATOR.join(notes)) <= 400
        assert "Dropped" in caplog.text
