from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from cline_hooks.core.frontends import FRONTENDS_BY_NAME
from cline_hooks.core.plugin import HooksPlugin, collect_hook_results, hookimpl, load_plugins
from cline_hooks.core.protocol import get_protocol
from cline_hooks.plugins.startup_blocks import (
    NOTE_SEPARATOR,
    RESERVE_CHARS,
    StartupBlock,
    StartupBlocksPlugin,
    block_header,
    block_text,
    budget,
    fallback_note,
    split_skill,
)
from cline_hooks.state.skills import is_skill_called

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

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


def run(hook_name: str = "TaskStart", source: str = "startup", **kwargs: object) -> list[str]:
    return collect_hook_results(
        load_plugins(), hook_name, task_id="task-1", workspace_roots=["/ws"], source=source, **kwargs
    ).notes


class TestEmission:
    def test_a_fresh_start_emits_the_block_text(self, use_plugins: Callable[..., None]) -> None:
        use_plugins(StartupBlocksPlugin(), contributor(block()))

        assert run() == [block_text(block(), "ALPHA BODY")]

    def test_a_subagent_gets_the_block_only_where_it_opts_in(self, use_plugins: Callable[..., None]) -> None:
        skipped = Mock(return_value="X")
        use_plugins(
            StartupBlocksPlugin(), contributor(block("alpha", skipped), block("beta", "BETA BODY", subagents=True))
        )

        notes = run(agent_id="sub-1")

        assert notes == [block_text(block("beta"), "BETA BODY")]
        skipped.assert_not_called()

    def test_a_subagent_start_gets_the_blocks_that_opt_in_to_subagents(self, use_plugins: Callable[..., None]) -> None:
        use_plugins(StartupBlocksPlugin(), contributor(block("alpha"), block("beta", "BETA BODY", subagents=True)))

        assert run("SubagentStart", source="", agent_id="sub-1") == [block_text(block("beta"), "BETA BODY")]

    @pytest.mark.parametrize(
        ("hook_name", "source"), [("TaskStart", "resume"), ("TaskStart", "compact"), ("TaskResume", "")]
    )
    def test_a_resume_gets_the_block_only_where_it_opts_in(
        self, use_plugins: Callable[..., None], hook_name: str, source: str
    ) -> None:
        skipped = Mock(return_value="X")
        use_plugins(
            StartupBlocksPlugin(), contributor(block("alpha", skipped), block("beta", "BETA BODY", on_resume=True))
        )

        notes = run(hook_name, source)

        assert notes == [block_text(block("beta"), "BETA BODY")]
        skipped.assert_not_called()

    def test_blocks_come_out_sorted_by_order_then_title(self, use_plugins: Callable[..., None]) -> None:
        use_plugins(
            StartupBlocksPlugin(),
            contributor(block("beta"), block("zeta", order=1)),
            contributor(block("alpha")),
        )

        titles = [note.splitlines()[0] for note in run()]

        assert titles == [block_header(title) for title in ("zeta", "alpha", "beta")]

    def test_no_contributors_inject_nothing(self, use_plugins: Callable[..., None]) -> None:
        use_plugins(StartupBlocksPlugin())

        assert run() == []

    def test_a_block_reads_as_a_header_a_statement_of_what_it_replaces_and_the_body(
        self, use_plugins: Callable[..., None]
    ) -> None:
        use_plugins(StartupBlocksPlugin(), contributor(block()))

        assert run() == ["Startup block: alpha\nResult of: do alpha. Already done - do not repeat it.\n\nALPHA BODY"]


class TestFallback:
    def test_a_raising_body_becomes_a_fallback_note_without_the_block_header(
        self, use_plugins: Callable[..., None], caplog: pytest.LogCaptureFixture
    ) -> None:
        broken = block("alpha", Mock(side_effect=RuntimeError("boom")))
        use_plugins(StartupBlocksPlugin(), contributor(broken))

        notes = run()

        assert notes == [fallback_note(broken)]
        assert block_header("alpha") not in notes[0]
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

    def test_a_missing_task_id_still_emits_the_block_without_recording_the_skill(
        self, use_plugins: Callable[..., None], mocker: MockerFixture
    ) -> None:
        record_skill = mocker.patch("cline_hooks.plugins.startup_blocks.record_skill")
        use_plugins(StartupBlocksPlugin(), contributor(block("alpha", "A", skill="alpha-skill")))

        notes = collect_hook_results(load_plugins(), "TaskStart", workspace_roots=["/ws"], source="startup").notes

        assert notes == [block_text(block(), "A")]
        record_skill.assert_not_called()


class TestBudget:
    def test_a_block_over_the_cap_becomes_a_fallback_note_within_budget(
        self, use_plugins: Callable[..., None], mocker: MockerFixture
    ) -> None:
        cap_budget(mocker, 400)
        fits, too_big = block("alpha", "A" * 50), block("beta", "B" * 1000)
        use_plugins(StartupBlocksPlugin(), contributor(fits, too_big))

        notes = run()

        assert notes == [block_text(fits, "A" * 50), fallback_note(too_big)]
        assert len(NOTE_SEPARATOR.join(notes)) <= 400
        assert block_header("beta") not in notes[1]

    def test_a_body_receives_the_characters_left_after_earlier_notes(
        self, use_plugins: Callable[..., None], mocker: MockerFixture
    ) -> None:
        cap_budget(mocker, 1000)
        first, second = block("alpha", "A" * 10), block("beta", Mock(return_value="B"))
        use_plugins(StartupBlocksPlugin(), contributor(first, second))

        run()

        used = len(block_text(first, "A" * 10)) + len(NOTE_SEPARATOR)
        second.body.assert_called_once_with(1000 - used - len(block_text(second, "")))  # type: ignore[attr-defined]

    @pytest.mark.parametrize("uncapped", ["no_cap", "no_spec"])
    def test_a_frontend_without_a_cap_gives_every_body_none(
        self, use_plugins: Callable[..., None], mocker: MockerFixture, uncapped: str
    ) -> None:
        if uncapped == "no_cap":
            cap_budget(mocker, None)
        else:
            mocker.patch.object(type(get_protocol()), "frontend_spec", None)
        huge = block("alpha", Mock(return_value="A" * 100_000))
        use_plugins(StartupBlocksPlugin(), contributor(huge))

        notes = run()

        huge.body.assert_called_once_with(None)  # type: ignore[attr-defined]
        assert notes == [block_text(huge, "A" * 100_000)]

    def test_a_block_with_no_room_left_for_a_body_becomes_a_fallback_without_calling_its_body(
        self, use_plugins: Callable[..., None], mocker: MockerFixture
    ) -> None:
        crowded = block("alpha", Mock(return_value="X"))
        cap_budget(mocker, len(block_text(crowded, "")))
        use_plugins(StartupBlocksPlugin(), contributor(crowded))

        notes = run()

        assert notes == [fallback_note(crowded)]
        crowded.body.assert_not_called()  # type: ignore[attr-defined]

    def test_many_over_cap_blocks_stay_within_budget_with_the_rest_dropped_and_logged(
        self, use_plugins: Callable[..., None], mocker: MockerFixture, caplog: pytest.LogCaptureFixture
    ) -> None:
        cap_budget(mocker, 300)
        blocks = [block(f"block-{index:02}", Mock(return_value="X" * 1000)) for index in range(50)]
        use_plugins(StartupBlocksPlugin(), contributor(*blocks))

        notes = run()

        assert len(NOTE_SEPARATOR.join(notes)) <= 300
        assert len(notes) < len(blocks)
        assert notes == [fallback_note(b) for b in blocks[: len(notes)]]
        assert "Dropped" in caplog.text

    def test_the_separator_between_notes_counts_against_the_budget(
        self, use_plugins: Callable[..., None], mocker: MockerFixture
    ) -> None:
        first, second = block("alpha", "A" * 10), block("beta", "B" * 10)
        without_separator = len(block_text(first, "A" * 10)) + len(block_text(second, "B" * 10))
        cap_budget(mocker, without_separator + len(NOTE_SEPARATOR) - 1)
        use_plugins(StartupBlocksPlugin(), contributor(first, second))

        notes = run()

        assert notes == [block_text(first, "A" * 10), fallback_note(second)]
        assert len(NOTE_SEPARATOR.join(notes)) <= without_separator + len(NOTE_SEPARATOR) - 1


class TestClaudeCodeBudget:
    def test_claude_code_leaves_the_reserve_out_of_its_cap(self, mocker: MockerFixture) -> None:
        mocker.patch.object(type(get_protocol()), "frontend_spec", FRONTENDS_BY_NAME["claude-code"])

        assert budget() == 10_000 - RESERVE_CHARS


class TestSplitSkill:
    def test_returns_the_frontmatter_lines_and_the_body(self, tmp_path: Path) -> None:
        path = tmp_path / "SKILL.md"
        path.write_text("---\nname: demo\nmetadata:\n  inject_at_start: true\n---\n\n# Demo\n\nBody text.\n")

        assert split_skill(path) == (["name: demo", "metadata:", "  inject_at_start: true"], "# Demo\n\nBody text.")

    def test_a_file_without_frontmatter_is_all_body(self, tmp_path: Path) -> None:
        path = tmp_path / "SKILL.md"
        path.write_text("# Demo\n")

        assert split_skill(path) == ([], "# Demo")
