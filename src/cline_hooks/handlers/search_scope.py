from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import os
from pathlib import Path
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cline_hooks.handlers.commands import ParsedCommand

MAX_SCAN_ENTRIES = 20_000
MAX_SCAN_SECONDS = 0.5

_GREP_TOOLS = frozenset({"grep", "egrep", "fgrep"})
_ALWAYS_RECURSIVE = frozenset({"rg", "ag", "ack", "fd", "fdfind", "find"})
_FD_TOOLS = frozenset({"fd", "fdfind"})
_IGNORE_AWARE = frozenset({"rg", "ag"}) | _FD_TOOLS
_PATTERN_TOOLS = _GREP_TOOLS | {"rg", "ag", "ack"} | _FD_TOOLS

_NO_IGNORE_FLAGS = frozenset({"-u", "-uu", "-uuu", "--unrestricted", "--no-ignore", "--hidden", "-."})
_FD_NO_IGNORE_FLAGS = frozenset({"-H", "-I"})
_PATTERN_VALUE_FLAGS = frozenset({"-e", "--regexp", "-f", "--file"})
_COMMON_VALUE_FLAGS = _PATTERN_VALUE_FLAGS | {"-A", "-B", "-C", "-m", "--max-count", "--context"}
_SCANNER_VALUE_FLAGS = frozenset(
    {"-g", "--glob", "-t", "--type", "-T", "--type-not", "-E", "--exclude", "-j", "--threads"}
    | {"-M", "--max-columns", "--max-filesize", "--max-depth", "--depth"}
)
_DEPTH_FLAGS = {
    "find": ("-maxdepth",),
    "rg": ("--max-depth", "-d"),
    "fd": ("--max-depth", "-d", "--exact-depth"),
    "fdfind": ("--max-depth", "-d", "--exact-depth"),
    "ag": ("--depth",),
}
_GLOB_CHARS = frozenset("*?[")
_UNRESOLVED_CHARS = ("$", "`")
_FIND_EXPRESSION_START = ("-", "(", "!")
_GITIGNORE_PATTERN_CHARS = frozenset("/*?[")
_DIRECTORY_CHANGERS = frozenset({"cd", "pushd"})
_PREVIOUS_DIRECTORY = "-"


@dataclass(frozen=True)
class SearchScope:
    """The directories a recursive search command would walk."""

    tool: str
    roots: tuple[str, ...]
    max_depth: int | None
    respects_ignores: bool


def _is_recursive(cmd: ParsedCommand) -> bool:
    """Return True when the command searches directories recursively."""
    if cmd.name in _ALWAYS_RECURSIVE:
        return True
    if cmd.name not in _GREP_TOOLS:
        return False
    return (
        bool({"--recursive", "--dereference-recursive", "--directories=recurse"} & set(cmd.words))
        or any(flag == "-d" and "recurse" in cmd.words for flag in cmd.flags)
        or any(not flag.startswith("--") and ("r" in flag or "R" in flag) for flag in cmd.flags)
    )


def _value_flags(tool: str) -> frozenset[str]:
    """Return the flags of a tool whose next word is a value, not a path."""
    flags = set(_COMMON_VALUE_FLAGS)
    if tool in _GREP_TOOLS:
        flags |= {"-d", "-D"}
    if tool in _IGNORE_AWARE:
        flags |= _SCANNER_VALUE_FLAGS
    if tool in _FD_TOOLS | {"rg"}:
        flags.add("-d")
    if tool in _FD_TOOLS:
        flags |= {"-e", "--extension", "--exact-depth"}
    return frozenset(flags)


def _max_depth(cmd: ParsedCommand) -> int | None:
    """Return the depth limit given to the command, or None when unlimited or not an integer."""
    for index, word in enumerate(cmd.words):
        for flag in _DEPTH_FLAGS.get(cmd.name, ()):
            if word == flag:
                value = cmd.words[index + 1] if index + 1 < len(cmd.words) else ""
            elif word.startswith(f"{flag}="):
                value = word[len(flag) + 1 :]
            elif flag == "-d" and word.startswith(flag) and not word.startswith("--"):
                value = word[len(flag) :]
            else:
                continue
            return int(value) if value.isdecimal() else None
    return None


def _positionals(cmd: ParsedCommand) -> list[str]:
    """Return the path-like words of the command, excluding flags, flag values and the search pattern."""
    if cmd.name == "find":
        positionals = []
        for word in cmd.words:
            if word.startswith(_FIND_EXPRESSION_START):
                break
            positionals.append(word)
        return positionals

    value_flags = _value_flags(cmd.name)
    positionals = []
    skip_next = False
    for word in cmd.words:
        if skip_next:
            skip_next = False
        elif word in value_flags:
            skip_next = True
        elif not word.startswith("-"):
            positionals.append(word)

    pattern_flags = _PATTERN_VALUE_FLAGS - {"-e"} if cmd.name in _FD_TOOLS else _PATTERN_VALUE_FLAGS
    if cmd.name in _PATTERN_TOOLS and not pattern_flags & set(cmd.words):
        return positionals[1:]
    return positionals


def _expand(word: str) -> str:
    """Return the word with environment variables and a leading ~ expanded."""
    return str(Path(os.path.expandvars(word)).expanduser())


def _resolve_root(word: str, cwd: str) -> str | None:
    """Return the absolute directory a search path word refers to, or None if it cannot be resolved."""
    path = _expand(word)
    if any(char in path for char in _UNRESOLVED_CHARS):
        return None
    glob_index = next((index for index, char in enumerate(path) if char in _GLOB_CHARS), None)
    if glob_index is not None:
        path = path[:glob_index].rpartition("/")[0] or ("/" if path.startswith("/") else "")
    return os.path.normpath(Path(cwd, path))


def search_scope(cmd: ParsedCommand, cwd: str) -> SearchScope | None:
    """Work out which directories a recursive search command would walk.

    Args:
        cmd: The parsed command.
        cwd: The directory the command runs in.

    Returns:
        The search scope, or None when the command is not a recursive search.
    """
    if not _is_recursive(cmd):
        return None
    no_ignore_flags = _NO_IGNORE_FLAGS | _FD_NO_IGNORE_FLAGS if cmd.name in _FD_TOOLS else _NO_IGNORE_FLAGS
    roots = tuple(root for word in _positionals(cmd) if (root := _resolve_root(word, cwd)) is not None)
    return SearchScope(
        tool=cmd.name,
        roots=roots or (cwd,),
        max_depth=_max_depth(cmd),
        respects_ignores=cmd.name in _IGNORE_AWARE and not no_ignore_flags & set(cmd.words),
    )


def effective_cwd(commands: list[ParsedCommand], index: int, session_cwd: str) -> str:
    """Return the directory the command at `index` runs in after replaying earlier cd/pushd commands.

    Args:
        commands: The commands of a shell command line, in order.
        index: The position of the command of interest.
        session_cwd: The directory the shell line starts in.

    Returns:
        The absolute directory the command runs in.
    """
    cwd = session_cwd
    for cmd in commands[:index]:
        if cmd.name not in _DIRECTORY_CHANGERS:
            continue
        target = next((word for word in cmd.words if word == _PREVIOUS_DIRECTORY or not word.startswith("-")), "~")
        if target != _PREVIOUS_DIRECTORY:
            cwd = os.path.normpath(Path(cwd, _expand(target)))
    return cwd


def is_home_or_above(path: str) -> bool:
    """Check whether a path is the filesystem root, the home directory, or one of its ancestors.

    Args:
        path: The directory to check.

    Returns:
        bool: True if the path is the root, the home directory or an ancestor of it.
    """
    resolved = Path(path).resolve()
    home = Path("~").expanduser().resolve()
    return resolved == home or resolved in home.parents


def _gitignored_names(directory: str) -> frozenset[str]:
    """Return the bare names listed in a directory's .gitignore.

    Args:
        directory: The directory holding the .gitignore.

    Returns:
        frozenset[str]: The entries that name a single file or directory, without patterns or path separators.
    """
    try:
        lines = Path(directory, ".gitignore").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return frozenset()
    names = (line.strip().removeprefix("/").removesuffix("/") for line in lines)
    return frozenset(
        name for name in names if name and not name.startswith(("#", "!")) and not _GITIGNORE_PATTERN_CHARS & set(name)
    )


def _count_entries(
    roots: tuple[str, ...],
    max_depth: int | None,
    respects_ignores: bool,
    entry_cap: int,
    stop: threading.Event,
) -> int:
    """Count directory entries under the roots, breadth first, until the cap or a stop request.

    Args:
        roots: The directories to walk.
        max_depth: The deepest level to descend to, or None for no limit.
        respects_ignores: Whether hidden entries and .gitignore names are skipped.
        entry_cap: The count at which to stop counting.
        stop: Set to abandon the walk early.

    Returns:
        int: The number of entries seen.
    """
    count = 0
    pending = deque((root, 0) for root in roots)
    while pending:
        if stop.is_set():
            return count
        directory, depth = pending.popleft()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        ignored = _gitignored_names(directory) if respects_ignores else frozenset()
        for entry in entries:
            if respects_ignores and (entry.name.startswith(".") or entry.name in ignored):
                continue
            count += 1
            if count >= entry_cap:
                return count
            if max_depth is None or depth + 1 < max_depth:
                try:
                    is_directory = entry.is_dir(follow_symlinks=False)
                except OSError:
                    is_directory = False
                if is_directory:
                    pending.append((entry.path, depth + 1))
    return count


def exceeds_scan_budget(scope: SearchScope, entry_cap: int, time_cap: float) -> bool:
    """Check whether walking a search scope exceeds the entry or time budget.

    Args:
        scope: The search scope to walk.
        entry_cap: The entry count at which the scope counts as too large.
        time_cap: The seconds after which a still-running walk counts as too large.

    Returns:
        bool: True if the walk reaches the entry cap or does not finish within the time cap.
    """
    stop = threading.Event()
    counts: list[int] = []
    walker = threading.Thread(
        target=lambda: counts.append(
            _count_entries(scope.roots, scope.max_depth, scope.respects_ignores, entry_cap, stop)
        ),
        daemon=True,
    )
    walker.start()
    walker.join(time_cap)
    if walker.is_alive():
        stop.set()
        return True
    return counts[0] >= entry_cap


def find_oversized_search(commands: list[ParsedCommand], session_cwd: str) -> SearchScope | None:
    """Find the first recursive search in a command line that would walk too large a tree.

    Args:
        commands: The commands of a shell command line, in order.
        session_cwd: The directory the shell line starts in.

    Returns:
        The scope of the first oversized search, or None if every search is small enough.
    """
    for index, cmd in enumerate(commands):
        scope = search_scope(cmd, effective_cwd(commands, index, session_cwd))
        if scope is None or scope.max_depth == 0:
            continue
        if (scope.max_depth is None and any(is_home_or_above(root) for root in scope.roots)) or exceeds_scan_budget(
            scope, MAX_SCAN_ENTRIES, MAX_SCAN_SECONDS
        ):
            return scope
    return None
