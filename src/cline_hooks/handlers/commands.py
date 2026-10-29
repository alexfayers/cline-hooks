from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise
import logging
from pathlib import Path
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    import bashlex.ast

logger = logging.getLogger("hooks.commands")


@dataclass(frozen=True)
class CommandRule:
    """Rule for blocking commands with specific flags."""

    command: str
    blocked_flags: frozenset[str] = field(default_factory=frozenset)
    message: str = "Command blocked"
    validator: Callable[[ParsedCommand, list[ParsedCommand]], bool] | None = None


@dataclass
class ParsedCommand:
    """Intermediate representation of a command extracted from a bashlex AST."""

    name: str
    flags: list[str]
    args: list[str]
    words: list[str] = field(default_factory=list, compare=False)
    piped_from: ParsedCommand | None = field(default=None, compare=False, repr=False)
    redirect_outputs: list[str] = field(default_factory=list, compare=False)
    redirect_inputs: list[str] = field(default_factory=list, compare=False)


def is_git_push(commands: list[ParsedCommand]) -> bool:
    """Check if any command in the list is a `git push`.

    Returns:
        bool: True if a `git push` command is present.
    """
    return any(cmd.name == "git" and "push" in cmd.args for cmd in commands)


_READ_ONLY_GIT_SUBCOMMANDS = frozenset({
    "status",
    "log",
    "diff",
    "show",
    "rev-parse",
    "ls-files",
    "blame",
    "merge-base",
    "rev-list",
    "cat-file",
    "describe",
    "shortlog",
    "grep",
    "ls-tree",
    "ls-remote",
    "for-each-ref",
    "show-ref",
    "name-rev",
    "diff-tree",
    "diff-index",
    "diff-files",
})
_BRANCH_LIST_FLAGS = frozenset({
    "--list",
    "-l",
    "--contains",
    "--no-contains",
    "--merged",
    "--no-merged",
    "--points-at",
})
_BRANCH_DISPLAY_FLAGS = frozenset({
    "--show-current",
    "--all",
    "--remotes",
    "--verbose",
    "--ignore-case",
    "--column",
    "--no-column",
    "--color",
    "--no-color",
    "--no-abbrev",
})
_BRANCH_DISPLAY_FLAG_PREFIXES = ("--abbrev=", "--sort=", "--format=")
_BRANCH_SHORT_FLAGS = re.compile(r"-[arvil]+")
_TAG_FLAGS = _BRANCH_LIST_FLAGS | _BRANCH_DISPLAY_FLAGS | {"-i"}
_STASH_REFLOG_FLAGS = frozenset({
    "-p",
    "--patch",
    "--stat",
    "--oneline",
    "--name-only",
    "--name-status",
    "--numstat",
    "--shortstat",
    "--no-patch",
    "--abbrev-commit",
    "--no-abbrev-commit",
    "--all",
})
_COUNT_FLAG = re.compile(r"-n\d*")


_GIT_OPTIONS_TAKING_A_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})


def _split_git_words(words: list[str]) -> tuple[str | None, list[str]]:
    """Split the words after `git` into its subcommand and the words after it.

    Returns:
        The subcommand (None if absent) and the words after it.
    """
    remaining = iter(enumerate(words))
    for index, word in remaining:
        if word in _GIT_OPTIONS_TAKING_A_VALUE:
            next(remaining, None)
        elif not word.startswith("-"):
            return word, words[index + 1 :]
    return None, []


def _is_branch_listing(words: list[str]) -> bool:
    """Check that `git branch` words only list branches.

    Returns:
        bool: True if every flag is a listing or display flag and any argument is a listing filter.
    """
    flags = [word for word in words if word.startswith("-")]
    short = [flag for flag in flags if _BRANCH_SHORT_FLAGS.fullmatch(flag)]
    listing = any(flag in _BRANCH_LIST_FLAGS for flag in flags) or any("l" in flag for flag in short)
    known = all(
        flag in _BRANCH_LIST_FLAGS | _BRANCH_DISPLAY_FLAGS or flag.startswith(_BRANCH_DISPLAY_FLAG_PREFIXES)
        for flag in flags
        if flag not in short
    )
    return known and (listing or len(flags) == len(words))


def _flags_known(words: list[str], known: frozenset[str] | set[str], prefixes: tuple[str, ...] = ()) -> bool:
    """Check that every flag is listed, starts with a listed prefix or is a `-n<count>` flag.

    Returns:
        bool: True if no flag falls outside those.
    """
    return all(
        word in known or word.startswith(prefixes) or _COUNT_FLAG.fullmatch(word)
        for word in words
        if word.startswith("-")
    )


def _is_tag_listing(words: list[str]) -> bool:
    """Check that `git tag` words only list tags; a pattern or ref needs `-l` or `--list`.

    Returns:
        bool: True if every flag is a listing flag and any argument comes with `-l` or `--list`.
    """
    flags = [word for word in words if word.startswith("-")]
    return _flags_known(words, _TAG_FLAGS, _BRANCH_DISPLAY_FLAG_PREFIXES) and (
        len(flags) == len(words) or "-l" in flags or "--list" in flags
    )


def _is_stash_or_reflog_listing(subcommand: str, words: list[str]) -> bool:
    """Check that `git stash` or `git reflog` words only show entries.

    Returns:
        bool: True for `stash list`, `stash show` and bare or `show` `reflog`, with only known flags.
    """
    if subcommand == "reflog" and not words:
        return True
    if not words or words[0] not in {"stash": {"list", "show"}, "reflog": {"show"}}[subcommand]:
        return False
    return _flags_known(words[1:], _STASH_REFLOG_FLAGS, ("--date=",))


def is_read_only_git(cmd: ParsedCommand) -> bool:
    """Check if a command is a read-only `git` subcommand, after any global options.

    Returns:
        bool: True if the command is `git` whose subcommand is read-only.
    """
    if cmd.name != "git":
        return False
    subcommand, words = _split_git_words(cmd.words)
    if subcommand == "branch":
        return _is_branch_listing(words)
    if subcommand == "tag":
        return _is_tag_listing(words)
    if subcommand in {"stash", "reflog"}:
        return _is_stash_or_reflog_listing(subcommand, words)
    return subcommand in _READ_ONLY_GIT_SUBCOMMANDS


def _iter_nodes(node: bashlex.ast.node) -> Iterator[bashlex.ast.node]:
    """Recursively yield all nodes in a bashlex AST.

    Yields:
        Iterator[bashlex.ast.node]: Every node in the tree.
    """
    import bashlex.ast  # ruff: ignore[import-outside-top-level]

    if not isinstance(node, bashlex.ast.node):
        return

    yield node

    for attr_name in ("parts", "list", "cmds", "thencmds", "elsecmds", "pipe"):
        if hasattr(node, attr_name):
            attr_value = getattr(node, attr_name)
            if isinstance(attr_value, list):
                for child in attr_value:
                    yield from _iter_nodes(child)


def _redirect_targets(parts: list[bashlex.ast.node], is_wanted_type: Callable[[str], bool]) -> list[str]:
    """Return the file names of the command's redirects whose operator satisfies the predicate."""
    return [
        part.output.word
        for part in parts
        if getattr(part, "kind", None) == "redirect"
        and is_wanted_type(part.type)
        and getattr(part.output, "kind", None) == "word"
    ]


def extract_commands(ast: list[bashlex.ast.node]) -> list[ParsedCommand]:
    """Traverse a bashlex AST and return all commands found.

    Returns:
        list[ParsedCommand]: The commands found in the AST.
    """
    commands = []

    for root in ast:
        parsed_by_node: dict[int, ParsedCommand] = {}
        feeders: dict[int, int] = {}
        for node in _iter_nodes(root):
            if getattr(node, "kind", None) == "pipeline":
                stages = [part for part in node.parts if getattr(part, "kind", None) != "pipe"]
                feeders.update({id(consumer): id(feeder) for feeder, consumer in pairwise(stages)})
            if getattr(node, "kind", None) != "command":
                continue

            parts = getattr(node, "parts", [])
            if not parts:
                continue

            first_part = parts[0]
            if getattr(first_part, "kind", None) != "word":
                continue

            cmd_name = getattr(first_part, "word", "")
            if not cmd_name:
                continue
            cmd_name = Path(cmd_name).name

            flags = []
            args = []
            words = []
            for part in parts[1:]:
                if getattr(part, "kind", None) == "word":
                    word = getattr(part, "word", "")
                    words.append(word)
                    if word.startswith("-"):
                        flags.append(word)
                    else:
                        args.append(word)

            feeder_id = feeders.get(id(node))
            command = ParsedCommand(
                name=cmd_name,
                flags=flags,
                args=args,
                words=words,
                piped_from=parsed_by_node.get(feeder_id) if feeder_id is not None else None,
                redirect_outputs=_redirect_targets(parts, lambda type_: type_.startswith((">", "&>"))),
                redirect_inputs=_redirect_targets(parts, lambda type_: type_ == "<"),
            )
            parsed_by_node[id(node)] = command
            commands.append(command)

    return commands


def matches_rule(
    cmd: ParsedCommand,
    rule: CommandRule,
    all_commands: list[ParsedCommand] | None = None,
) -> bool:
    """Check if a command violates a rule.

    Returns:
        bool: True if the command matches (violates) the rule.
    """
    if cmd.name != rule.command:
        return False

    if not rule.blocked_flags and not rule.validator:
        return True

    if rule.validator and rule.validator(cmd, all_commands or []):
        return True

    for blocked_flag in rule.blocked_flags:
        if blocked_flag.startswith("--"):
            if blocked_flag in cmd.flags:
                return True
        elif len(blocked_flag) >= 2 and blocked_flag[0] == "-":  # ruff: ignore[magic-value-comparison]
            flag_char = blocked_flag[1]
            for cmd_flag in cmd.flags:
                if cmd_flag.startswith("-") and not cmd_flag.startswith("--") and flag_char in cmd_flag[1:]:
                    return True

    return False


def check_rules(commands: list[ParsedCommand], rules: list[CommandRule]) -> CommandRule | None:
    """Return the first violated rule, or None if all commands are clean."""
    for cmd in commands:
        for rule in rules:
            if matches_rule(cmd, rule, commands):
                logger.info("Command %s matches rule %s", cmd, rule)
                return rule
    return None


def extract_replacement_blocks(diff: str) -> list[str]:
    """Extract replacement content from SEARCH/REPLACE diff blocks.

    Format:
    - ``------- SEARCH`` starts a search block
    - ``=======`` ends search, starts replacement
    - ``+++++++ REPLACE`` ends replacement block

    Returns:
        list[str]: The replacement blocks found.
    """
    blocks = []
    lines = diff.split("\n")
    in_search = False
    in_replace = False
    current_block: list[str] = []

    for line in lines:
        stripped = line.strip()

        if stripped == "------- SEARCH":
            in_search = True
            in_replace = False
            current_block = []
        elif stripped == "=======" and in_search:
            in_search = False
            in_replace = True
            current_block = []
        elif stripped == "+++++++ REPLACE" and in_replace:
            blocks.append("\n".join(current_block))
            in_replace = False
            current_block = []
        elif in_replace:
            current_block.append(line)

    return blocks


def strip_strings(line: str) -> str:
    """Remove quoted strings to avoid false positives in comment detection.

    Returns:
        str: The line with string literals replaced by empty quotes.
    """
    line = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '""', line)
    return re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", "''", line)


def contains_comment(line: str) -> bool:
    """Detect if a line contains a comment, avoiding false positives.

    Returns:
        bool: True if the line contains a comment.
    """
    stripped_line = strip_strings(line)

    if re.search(r"(?<!:)//", stripped_line):
        return True

    return bool(re.search(r"^[^#]*#(?!!).*", stripped_line))
