from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re
from typing import TYPE_CHECKING

import bashlex.ast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from cline_hooks.core.plugin import HooksPlugin

logger = logging.getLogger("hooks")


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


def validate_git_commit_message(cmd: ParsedCommand, _all: list[ParsedCommand]) -> bool:
    """Check if a git commit message contains newlines.

    Returns:
        bool: True if the message is invalid (contains newlines).
    """
    if "commit" not in cmd.args:
        return False

    for flag in cmd.flags:
        if flag in {"-m", "--message"}:
            msg_idx = (
                cmd.flags.index(flag) + 1 + len([a for a in cmd.args if cmd.args.index(a) < cmd.flags.index(flag)])
            )
            all_words = cmd.args + cmd.flags
            if msg_idx < len(all_words):
                message = all_words[msg_idx]
                return "\n" in message
        elif flag.startswith("--message="):
            message = flag[10:]
            return "\n" in message

    return False


def is_git_push(commands: list[ParsedCommand]) -> bool:
    """Check if any command in the list is a `git push`.

    Returns:
        bool: True if a `git push` command is present.
    """
    return any(cmd.name == "git" and "push" in cmd.args for cmd in commands)


def get_all_build_commands(plugins: list[HooksPlugin]) -> frozenset[str]:
    """Aggregate build command names from all plugins.

    Args:
        plugins: The loaded plugin instances.

    Returns:
        frozenset of all build command names across all plugins.
    """
    result: set[str] = set()
    for plugin in plugins:
        result |= plugin.get_build_commands()
    return frozenset(result)


def get_all_command_rules(plugins: list[HooksPlugin]) -> list[CommandRule]:
    """Aggregate command rules from all plugins.

    Args:
        plugins: The loaded plugin instances.

    Returns:
        List of all CommandRule instances across all plugins.
    """
    result: list[CommandRule] = []
    for plugin in plugins:
        result.extend(plugin.get_command_rules())
    return result


def _iter_nodes(node: bashlex.ast.node) -> Iterator[bashlex.ast.node]:
    """Recursively yield all nodes in a bashlex AST.

    Yields:
        Iterator[bashlex.ast.node]: Every node in the tree.
    """
    if not isinstance(node, bashlex.ast.node):
        return

    yield node

    for attr_name in ("parts", "list", "cmds", "thencmds", "elsecmds", "pipe"):
        if hasattr(node, attr_name):
            attr_value = getattr(node, attr_name)
            if isinstance(attr_value, list):
                for child in attr_value:
                    yield from _iter_nodes(child)


def extract_commands(ast: list[bashlex.ast.node]) -> list[ParsedCommand]:
    """Traverse a bashlex AST and return all commands found.

    Returns:
        list[ParsedCommand]: The commands found in the AST.
    """
    commands = []

    for root in ast:
        for node in _iter_nodes(root):
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

            flags = []
            args = []
            for part in parts[1:]:
                if getattr(part, "kind", None) == "word":
                    word = getattr(part, "word", "")
                    if word.startswith("-"):
                        flags.append(word)
                    else:
                        args.append(word)

            commands.append(ParsedCommand(name=cmd_name, flags=flags, args=args))

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
        elif len(blocked_flag) >= 2 and blocked_flag[0] == "-":  # noqa: PLR2004
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
