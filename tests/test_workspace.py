from __future__ import annotations

from cline_hooks.state import workspace


class TestShouldNoteWorkspaceChange:
    def test_first_sighting_is_silent(self) -> None:
        assert workspace.should_note_workspace_change("t", ["/a"]) is False

    def test_same_roots_twice_no_note(self) -> None:
        assert workspace.should_note_workspace_change("t", ["/a"]) is False
        assert workspace.should_note_workspace_change("t", ["/a"]) is False

    def test_changed_roots_fires(self) -> None:
        workspace.should_note_workspace_change("t", ["/a"])
        assert workspace.should_note_workspace_change("t", ["/b"]) is True

    def test_change_back_to_previous_dir_fires_again(self) -> None:
        workspace.should_note_workspace_change("t", ["/a"])
        assert workspace.should_note_workspace_change("t", ["/b"]) is True
        assert workspace.should_note_workspace_change("t", ["/a"]) is True

    def test_fires_once_per_move(self) -> None:
        workspace.should_note_workspace_change("t", ["/a"])
        assert workspace.should_note_workspace_change("t", ["/b"]) is True
        assert workspace.should_note_workspace_change("t", ["/b"]) is False

    def test_reordered_multi_root_counts_as_change(self) -> None:
        workspace.should_note_workspace_change("t", ["/a", "/b"])
        assert workspace.should_note_workspace_change("t", ["/b", "/a"]) is True

    def test_appended_root_counts_as_change(self) -> None:
        workspace.should_note_workspace_change("t", ["/a"])
        assert workspace.should_note_workspace_change("t", ["/a", "/b"]) is True

    def test_empty_roots_never_fires(self) -> None:
        assert workspace.should_note_workspace_change("t", []) is False

    def test_empty_roots_do_not_clobber_recorded_value(self) -> None:
        workspace.should_note_workspace_change("t", ["/a"])
        assert workspace.should_note_workspace_change("t", []) is False
        assert workspace.should_note_workspace_change("t", ["/a"]) is False

    def test_independent_sessions(self) -> None:
        workspace.should_note_workspace_change("a", ["/x"])
        workspace.should_note_workspace_change("b", ["/y"])
        assert workspace.should_note_workspace_change("a", ["/z"]) is True
        assert workspace.should_note_workspace_change("b", ["/y"]) is False


class TestRecordWorkspace:
    def test_record_then_same_roots_no_note(self) -> None:
        workspace.record_workspace("t", ["/a"])
        assert workspace.should_note_workspace_change("t", ["/a"]) is False

    def test_record_then_different_roots_fires(self) -> None:
        workspace.record_workspace("t", ["/a"])
        assert workspace.should_note_workspace_change("t", ["/b"]) is True

    def test_record_empty_roots_is_noop(self) -> None:
        workspace.record_workspace("t", [])
        assert workspace.should_note_workspace_change("t", ["/a"]) is False


class TestReset:
    def test_reset_makes_next_call_a_silent_reseed(self) -> None:
        workspace.should_note_workspace_change("t", ["/a"])
        workspace.reset("t")
        assert workspace.should_note_workspace_change("t", ["/a"]) is False

    def test_reset_nonexistent_is_noop(self) -> None:
        workspace.reset("nonexistent-task")

    def test_reset_does_not_affect_other_tasks(self) -> None:
        workspace.should_note_workspace_change("a", ["/x"])
        workspace.should_note_workspace_change("b", ["/y"])
        workspace.reset("a")
        assert workspace.should_note_workspace_change("b", ["/y"]) is False
