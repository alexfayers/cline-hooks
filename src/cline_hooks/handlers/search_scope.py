from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
import os
from pathlib import Path
import shlex
import subprocess
import threading

from cline_hooks.handlers.commands import ParsedCommand, extract_commands, parse_command
from cline_hooks.handlers.git_context import GIT_TIMEOUT_SECONDS

MAX_SCAN_ENTRIES = 20_000
MAX_SCAN_SECONDS = 0.5

_GREP_TOOLS = frozenset({"grep", "egrep", "fgrep"})
_STDIN_READERS = _GREP_TOOLS | {"rg"}
_ALWAYS_RECURSIVE = frozenset({"rg", "ag", "ack", "fd", "fdfind", "find"})
_FD_TOOLS = frozenset({"fd", "fdfind"})
_IGNORE_AWARE = frozenset({"rg", "ag"}) | _FD_TOOLS
_PATTERN_TOOLS = _GREP_TOOLS | {"rg", "ag", "ack"} | _FD_TOOLS

_NO_IGNORE_FLAGS = frozenset({"-u", "-uu", "-uuu", "--unrestricted", "--no-ignore", "--hidden", "-."})
_FD_NO_IGNORE_FLAGS = frozenset({"-H", "-I"})
_PATTERN_VALUE_FLAGS = frozenset({"--regexp", "--file"})
_PATTERN_LETTERS = "ef"
_GREP_VALUE_FLAGS = _PATTERN_VALUE_FLAGS | {
    "--after-context",
    "--before-context",
    "--context",
    "--max-count",
    "--include",
    "--exclude",
    "--exclude-dir",
    "--exclude-from",
    "--label",
    "--binary-files",
    "--directories",
    "--devices",
}
_RG_VALUE_FLAGS = _PATTERN_VALUE_FLAGS | {
    "--after-context",
    "--before-context",
    "--context",
    "--max-count",
    "--glob",
    "--iglob",
    "--type",
    "--type-not",
    "--type-add",
    "--type-clear",
    "--max-depth",
    "--max-filesize",
    "--max-columns",
    "--threads",
    "--encoding",
    "--replace",
    "--sort",
    "--sortr",
    "--pre",
    "--pre-glob",
    "--ignore-file",
    "--colors",
    "--color",
    "--context-separator",
    "--field-context-separator",
    "--field-match-separator",
    "--path-separator",
    "--engine",
    "--dfa-size-limit",
    "--regex-size-limit",
}
_FD_VALUE_FLAGS = frozenset({
    "--extension",
    "--exclude",
    "--type",
    "--max-depth",
    "--min-depth",
    "--exact-depth",
    "--size",
    "--changed-within",
    "--changed-before",
    "--newer",
    "--older",
    "--owner",
    "--color",
    "--threads",
    "--max-results",
    "--base-directory",
    "--search-path",
    "--ignore-file",
    "--and",
    "--format",
    "--batch-size",
    "--exec",
    "--exec-batch",
})
_LEGACY_VALUE_FLAGS = _PATTERN_VALUE_FLAGS | {
    "--max-count",
    "--context",
    "--glob",
    "--type",
    "--type-not",
    "--exclude",
    "--threads",
    "--max-columns",
    "--max-filesize",
    "--max-depth",
    "--depth",
}
_LONG_VALUE_FLAGS = {"grep": _GREP_VALUE_FLAGS, "rg": _RG_VALUE_FLAGS, "fd": _FD_VALUE_FLAGS}
_SHORT_VALUE_LETTERS = {"grep": "efABCmdD", "rg": "efABCmgtTEjMdr", "fd": "eEtdSjcoxXC", "ag": "efABCmgtTEjM"}
_FD_EXEC_LETTERS = frozenset("xX")
_FD_EXEC_FLAGS = frozenset({"--exec", "--exec-batch"})
_FD_SEARCH_PATH_FLAG = "--search-path"
_FD_BASE_DIRECTORY_FLAG = "--base-directory"
_FD_BASE_DIRECTORY_LETTER = "C"
_REWRITABLE_TOOLS = frozenset({"rg", "find"}) | _GREP_TOOLS | _FD_TOOLS
_CLUSTER_START = "-"
_END_OF_OPTIONS = "--"
_RG_LIST_FLAGS = frozenset({"--files", "--type-list"})
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
_FIND_GLOBAL_FLAGS = frozenset({"-H", "-L", "-P"})
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
    command: ParsedCommand
    pathless: bool


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


@dataclass(frozen=True)
class _Arguments:
    """The words of a search command that are not flags or flag values."""

    positionals: list[str]
    pattern_given_by_flag: bool
    short_flags: frozenset[str]
    long_flags: frozenset[str]
    search_paths: list[str]
    base_directory: str | None

    @property
    def pattern_is_positional(self) -> bool:
        """Whether the first positional is the search pattern."""
        return not self.pattern_given_by_flag and not self.long_flags & _RG_LIST_FLAGS


def _tool_family(name: str) -> str:
    """Return the key of the tool's flag tables: grep, rg, fd, or ag for the other pattern tools."""
    if name in _GREP_TOOLS:
        return "grep"
    return "fd" if name in _FD_TOOLS else name


def _parse_arguments(cmd: ParsedCommand) -> _Arguments:
    """Split the words of a grep, rg, fd, ag or ack command into positionals, flags and flag values.

    Returns:
        The positional words, whether a flag supplies the pattern, the flags seen, and any `fd --search-path` and
        `fd --base-directory` values.
    """
    family = _tool_family(cmd.name)
    long_values = _LONG_VALUE_FLAGS.get(family, _LEGACY_VALUE_FLAGS)
    short_values = _SHORT_VALUE_LETTERS.get(family, "efABCm")
    pattern_letters = "" if family == "fd" else _PATTERN_LETTERS
    positionals: list[str] = []
    search_paths: list[str] = []
    base_directory: str | None = None
    short_flags: set[str] = set()
    long_flags: set[str] = set()
    pattern_given_by_flag = False
    options_ended = False
    words = iter(cmd.words)
    for word in words:
        if options_ended or not word.startswith(_CLUSTER_START) or word == _CLUSTER_START:
            positionals.append(word)
        elif word == _END_OF_OPTIONS:
            options_ended = True
        elif word.startswith(_END_OF_OPTIONS):
            name, has_value, value = word.partition("=")
            long_flags.add(name)
            pattern_given_by_flag |= family != "fd" and name in _PATTERN_VALUE_FLAGS
            if name in long_values:
                value = value if has_value else next(words, "")
                if name == _FD_SEARCH_PATH_FLAG:
                    search_paths.append(value)
                elif name == _FD_BASE_DIRECTORY_FLAG:
                    base_directory = value
        else:
            for index, letter in enumerate(word[1:], 1):
                short_flags.add(letter)
                if letter in short_values:
                    pattern_given_by_flag |= letter in pattern_letters
                    value = word[index + 1 :] or next(words, "")
                    if family == "fd" and letter == _FD_BASE_DIRECTORY_LETTER:
                        base_directory = value
                    break
    return _Arguments(
        positionals, pattern_given_by_flag, frozenset(short_flags), frozenset(long_flags), search_paths, base_directory
    )


def _find_leading_options(words: list[str]) -> int:
    """Return how many leading words of a `find` command are global options (-H, -L, -P, -D debugopts, -Olevel)."""
    count = 0
    while count < len(words):
        if words[count] in _FIND_GLOBAL_FLAGS or words[count].startswith("-O"):
            count += 1
        elif words[count] == "-D":
            count += 2
        else:
            break
    return count


def _positionals(cmd: ParsedCommand) -> list[str]:
    """Return the path-like words of the command, excluding flags, flag values and the search pattern."""
    if cmd.name == "find":
        positionals = []
        for word in cmd.words[_find_leading_options(cmd.words) :]:
            if word.startswith(_FIND_EXPRESSION_START):
                break
            positionals.append(word)
        return positionals

    arguments = _parse_arguments(cmd)
    positionals = arguments.positionals
    if cmd.name in _PATTERN_TOOLS and arguments.pattern_is_positional:
        positionals = positionals[1:]
    return positionals + arguments.search_paths


def _reads_pipe(cmd: ParsedCommand) -> bool:
    """Return True when a pathless grep or rg reads the output of the previous pipeline command."""
    return cmd.piped_from is not None and cmd.name in _STDIN_READERS and not _positionals(cmd)


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
    if _reads_pipe(cmd):
        return None
    no_ignore_flags = _NO_IGNORE_FLAGS | _FD_NO_IGNORE_FLAGS if cmd.name in _FD_TOOLS else _NO_IGNORE_FLAGS
    positionals = _positionals(cmd)
    base_directory = _parse_arguments(cmd).base_directory if cmd.name in _FD_TOOLS else None
    cwd = (base_directory and _resolve_root(base_directory, cwd)) or cwd
    roots = tuple(root for word in positionals if (root := _resolve_root(word, cwd)) is not None)
    return SearchScope(
        tool=cmd.name,
        roots=roots or (cwd,),
        max_depth=_max_depth(cmd),
        respects_ignores=cmd.name in _IGNORE_AWARE and not no_ignore_flags & set(cmd.words),
        command=cmd,
        pathless=not positionals,
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


def _is_oversized(scope: SearchScope) -> bool:
    """Check whether a search would walk the filesystem root, the home directory, or too large a tree.

    Returns:
        bool: True if the search is unbounded at the home directory or above, or exceeds the scan budget.
    """
    if scope.max_depth == 0:
        return False
    return (scope.max_depth is None and any(is_home_or_above(root) for root in scope.roots)) or exceeds_scan_budget(
        scope, MAX_SCAN_ENTRIES, MAX_SCAN_SECONDS
    )


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
        if scope is not None and _is_oversized(scope):
            return scope
    return None


def _is_git_ignored(root: str, path: str) -> bool:
    """Return whether git's ignore rules in `root` exclude `path`; False where git cannot tell."""
    try:
        return (
            subprocess.run(
                ["git", "-C", root, "check-ignore", "-q", "--", path],  # ruff: ignore[start-process-with-partial-path]
                capture_output=True,
                timeout=GIT_TIMEOUT_SECONDS,
                check=False,
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def _omits_start(scope: SearchScope, root: str) -> bool:
    """Return whether searching `root` instead of the scope's directory would skip that directory.

    Returns:
        bool: True if the tool skips hidden or git-ignored directories and `root` is above the scope's directory
            and reaches it through one.
    """
    start = Path(scope.roots[0])
    if not scope.respects_ignores or start == Path(root) or not start.is_relative_to(root):
        return False
    return any(part.startswith(".") for part in start.relative_to(root).parts) or _is_git_ignored(root, str(start))


def _narrower_root(scope: SearchScope, workspace_roots: list[str]) -> str | None:
    """Find a workspace root to search instead of the oversized directory.

    Returns:
        The first workspace root that is small enough and does not skip the oversized directory, or None.
    """
    return next(
        (
            root
            for root in workspace_roots
            if root not in scope.roots
            and not _omits_start(scope, root)
            and not _is_oversized(replace(scope, roots=(root,)))
        ),
        None,
    )


def _insertion(scope: SearchScope, root: str) -> tuple[int, str] | None:
    """Work out where in the command line, and what, to insert so the search covers `root`.

    Returns:
        The offset and text to insert, or None where the tool is not one the rewrite supports.
    """
    cmd = scope.command
    if cmd.name not in _REWRITABLE_TOOLS:
        return None
    path = f" {shlex.quote(root)}"
    if cmd.name == "find":
        leading = min(_find_leading_options(cmd.words), len(cmd.word_ends))
        return (cmd.word_ends[leading - 1] if leading else cmd.name_end), path
    offset = cmd.word_ends[-1] if cmd.word_ends else cmd.name_end
    if cmd.name in _FD_TOOLS:
        arguments = _parse_arguments(cmd)
        if arguments.short_flags & _FD_EXEC_LETTERS or arguments.long_flags & _FD_EXEC_FLAGS:
            return None
        if not arguments.positionals:
            return offset, f" ''{path}"
    return offset, path


def scope_oversized_searches(command: str, session_cwd: str, workspace_roots: list[str]) -> str | None:
    """Give every oversized pathless search in a command line a smaller workspace root as its path.

    Args:
        command: The shell command line.
        session_cwd: The directory the shell line starts in.
        workspace_roots: The workspace directories to search instead.

    Returns:
        The command line with the paths added, or None if an oversized search cannot be scoped to a smaller tree.
    """
    commands = extract_commands(parse_command(command))
    for _ in range(len(commands) + 1):
        scope = find_oversized_search(commands, session_cwd)
        if scope is None:
            return command
        root = _narrower_root(scope, workspace_roots) if scope.pathless else None
        insertion = root and _insertion(scope, root)
        if not insertion:
            return None
        offset, text = insertion
        command = command[:offset] + text + command[offset:]
        commands = extract_commands(parse_command(command))
    return None
