from __future__ import annotations

import bashlex

from cline_hooks.handlers.commands import (
    ParsedCommand,
    contains_comment,
    extract_commands,
    extract_replacement_blocks,
    is_git_push,
    strip_strings,
)


class TestExtractCommands:
    def test_uses_basename_for_absolute_path_commands(self) -> None:
        commands = extract_commands(bashlex.parse("/usr/bin/git push"))
        assert commands == [ParsedCommand(name="git", flags=[], args=["push"])]

    def test_uses_bare_name_unchanged(self) -> None:
        commands = extract_commands(bashlex.parse("git push"))
        assert commands == [ParsedCommand(name="git", flags=[], args=["push"])]


class TestIsGitPush:
    def test_detects_git_push(self) -> None:
        commands = [ParsedCommand(name="git", flags=[], args=["push"])]
        assert is_git_push(commands) is True

    def test_ignores_other_git_subcommands(self) -> None:
        commands = [ParsedCommand(name="git", flags=[], args=["commit"])]
        assert is_git_push(commands) is False

    def test_ignores_non_git_commands(self) -> None:
        commands = [ParsedCommand(name="push", flags=[], args=[])]
        assert is_git_push(commands) is False

    def test_detects_git_push_among_other_commands(self) -> None:
        commands = [
            ParsedCommand(name="cd", flags=[], args=["subdir"]),
            ParsedCommand(name="git", flags=[], args=["push"]),
        ]
        assert is_git_push(commands) is True


class TestExtractReplacementBlocks:
    def test_extracts_single_block(self) -> None:
        diff = "------- SEARCH\nold\n=======\nnew content\n+++++++ REPLACE"
        assert extract_replacement_blocks(diff) == ["new content"]

    def test_extracts_multiple_blocks(self) -> None:
        diff = (
            "------- SEARCH\nold1\n=======\nnew1\n+++++++ REPLACE\n"
            "------- SEARCH\nold2\n=======\nnew2\n+++++++ REPLACE"
        )
        assert extract_replacement_blocks(diff) == ["new1", "new2"]

    def test_no_markers_returns_empty_list(self) -> None:
        assert extract_replacement_blocks("no markers here") == []

    def test_unclosed_replace_block_is_dropped(self) -> None:
        diff = "------- SEARCH\nold\n=======\nnew content"
        assert extract_replacement_blocks(diff) == []

    def test_multiline_replacement_is_preserved(self) -> None:
        diff = "------- SEARCH\nold\n=======\nline1\nline2\n+++++++ REPLACE"
        assert extract_replacement_blocks(diff) == ["line1\nline2"]


class TestStripStrings:
    def test_strips_double_quoted_string(self) -> None:
        assert strip_strings('x = "hello world"') == 'x = ""'

    def test_strips_single_quoted_string(self) -> None:
        assert strip_strings("x = 'hello world'") == "x = ''"

    def test_preserves_escaped_quotes_within_string(self) -> None:
        assert strip_strings('x = "a \\"quoted\\" value"') == 'x = ""'

    def test_leaves_unquoted_text_unchanged(self) -> None:
        assert strip_strings("x = 1 + 2") == "x = 1 + 2"


class TestContainsComment:
    def test_detects_hash_comment(self) -> None:
        assert contains_comment("x = 1  # comment") is True

    def test_detects_double_slash_comment(self) -> None:
        assert contains_comment("x = 1;  // comment") is True

    def test_hash_inside_string_is_not_a_comment(self) -> None:
        assert contains_comment('x = "#not-a-comment"') is False

    def test_double_slash_inside_string_is_not_a_comment(self) -> None:
        assert contains_comment('x = "https://example.com"') is False

    def test_shebang_is_not_a_comment(self) -> None:
        assert contains_comment("#!/usr/bin/env python") is False

    def test_no_comment_returns_false(self) -> None:
        assert contains_comment("x = 1 + 2") is False
