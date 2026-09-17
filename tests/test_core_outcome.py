from __future__ import annotations

from cline_hooks.core.outcome import Disposition, Outcome


class TestMessage:
    def test_none_when_no_notes(self) -> None:
        assert Outcome().message is None

    def test_joined_with_blank_lines(self) -> None:
        outcome = Outcome.allow("first", "second")
        assert outcome.message == "first\n\nsecond"


class TestAllow:
    def test_drops_empty_and_blank_notes(self) -> None:
        outcome = Outcome.allow("kept", "", "   ")
        assert outcome.notes == ("kept",)

    def test_disposition_is_allow(self) -> None:
        assert Outcome.allow("note").disposition is Disposition.ALLOW


class TestBlock:
    def test_reason_is_the_single_note(self) -> None:
        outcome = Outcome.block("bad command")
        assert outcome.notes == ("bad command",)
        assert outcome.disposition is Disposition.BLOCK


class TestFeedback:
    def test_message_is_the_single_note(self) -> None:
        outcome = Outcome.feedback("trace text")
        assert outcome.notes == ("trace text",)
        assert outcome.disposition is Disposition.FEEDBACK


class TestMergeIdentity:
    def test_empty_merge_empty_is_empty(self) -> None:
        assert Outcome().merge(Outcome()) == Outcome()

    def test_empty_left_identity(self) -> None:
        other = Outcome.allow("note", label="X", user_message="user")
        assert Outcome().merge(other) == other

    def test_empty_right_identity(self) -> None:
        first = Outcome.allow("note", label="X", user_message="user")
        assert first.merge(Outcome()) == first


class TestMergeNotesAccumulate:
    def test_notes_accumulate_in_contribution_order(self) -> None:
        merged = Outcome.allow("first").merge(Outcome.allow("second"))
        assert merged.notes == ("first", "second")


class TestMergeBlockPrecedence:
    def test_first_block_wins_over_later_block(self) -> None:
        first_block = Outcome.block("first reason")
        merged = first_block.merge(Outcome.block("second reason"))
        assert merged == first_block

    def test_block_discards_notes_accumulated_before_it(self) -> None:
        merged = Outcome.allow("earlier note").merge(Outcome.block("blocked"))
        assert merged.notes == ("blocked",)
        assert merged.disposition is Disposition.BLOCK

    def test_notes_after_a_block_are_discarded(self) -> None:
        merged = Outcome.block("blocked").merge(Outcome.allow("later note"))
        assert merged.notes == ("blocked",)
        assert merged.disposition is Disposition.BLOCK


class TestMergeUserMessage:
    def test_accumulates_across_allow_and_allow(self) -> None:
        merged = Outcome.allow(user_message="first").merge(Outcome.allow(user_message="second"))
        assert merged.user_message == "first\n\nsecond"

    def test_accumulates_across_a_block(self) -> None:
        merged = Outcome.allow(user_message="first").merge(
            Outcome(Disposition.BLOCK, notes=("blocked",), user_message="second")
        )
        assert merged.user_message == "first\n\nsecond"


class TestMergeLabel:
    def test_first_non_empty_label_wins(self) -> None:
        merged = Outcome.allow("a", label="FIRST").merge(Outcome.allow("b", label="SECOND"))
        assert merged.label == "FIRST"

    def test_later_label_used_when_first_is_empty(self) -> None:
        merged = Outcome.allow("a").merge(Outcome.allow("b", label="SECOND"))
        assert merged.label == "SECOND"

    def test_later_label_never_overwrites_earlier(self) -> None:
        merged = Outcome.allow("a", label="FIRST").merge(Outcome.block("bad"))
        assert merged.label == "FIRST"


class TestMergeFeedbackDisposition:
    def test_feedback_and_allow_stays_feedback(self) -> None:
        merged = Outcome.feedback("trace").merge(Outcome.allow("note"))
        assert merged.disposition is Disposition.FEEDBACK

    def test_allow_and_feedback_becomes_feedback(self) -> None:
        merged = Outcome.allow("note").merge(Outcome.feedback("trace"))
        assert merged.disposition is Disposition.FEEDBACK
