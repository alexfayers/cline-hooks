from __future__ import annotations

import logging
import os
from pathlib import Path, PurePosixPath
import re
from typing import TYPE_CHECKING, Any, cast

from cline_hooks.core.parameters import ReadParameters, ShellParameters, SkillParameters
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.vocabulary import SHELL_TOOLS, CanonicalTool
from cline_hooks.handlers.commands import extract_commands
from cline_hooks.handlers.search_scope import effective_cwd
from cline_hooks.state.jsonfile import discard_key, discard_prefix, read_json, updated_json
from cline_hooks.state.paths import get_data_dir

if TYPE_CHECKING:
    from cline_hooks.handlers.commands import ParsedCommand

logger = logging.getLogger("hooks.state.skills")

_SKILL_REQUIREMENTS: dict[str, str] = {
    "git": "git-usage",
    "cr": "cr",
}

_FILE_READERS = frozenset({"cat", "sed", "head", "tail", "less", "more", "bat", "nl", "tac", "awk"})

_PROGRAM_READERS = frozenset({"sed", "awk"})
_PROGRAM_OPTION = re.compile(r"-[nrEszu]*[ef]|--expression|--file")
_ATTACHED_PROGRAM_OPTION = re.compile(r"-[nrEszu]*[ef].+|--(?:expression|file)=.+")
_AWK_VALUE_OPTION = re.compile(r"-[vF]")

_WRAP_UP_SKILLS = frozenset({"session-end", "handoff"})

_STATE_PATH = get_data_dir() / "skill-state.json"


def record_skill(task_id: str, skill_name: str) -> None:
    """Record that a skill has been called for a task.

    Args:
        task_id: The session or task identifier.
        skill_name: The skill name or `<skill>/<part>.md` key.
    """
    with updated_json(_STATE_PATH, cast("dict[str, list[str]]", {})) as data:
        skills = set(data.get(task_id, []))
        skills.add(skill_name)
        data[task_id] = sorted(skills)


def is_skill_called(task_id: str, skill_name: str) -> bool:
    """Check whether a skill has been called for a task.

    Args:
        task_id: The session or task identifier.
        skill_name: The skill name or `<skill>/<part>.md` key.

    Returns:
        True if the skill has been called for the task.
    """
    data: dict[str, list[str]] = read_json(_STATE_PATH, {})
    return skill_name in data.get(task_id, [])


def installed_skill_file(key: str) -> Path | None:
    """Return the installed file for a skill name or `<skill>/<part>.md` key, or None where it is not installed."""
    spec = get_protocol().frontend_spec
    if spec is None or spec.skills_dir is None:
        return None
    path = spec.skills_dir() / (key if "/" in key else f"{key}/SKILL.md")
    return path if path.is_file() else None


def skill_key(path: str, cwd: str = ".") -> str | None:
    """Return the skill name for a SKILL.md path, or `<skill>/<part>.md` for the installed copy of a skill part.

    Args:
        path: The file path read.
        cwd: The directory a relative path is read from.

    Returns:
        The skill name or part key, or None for any other file, including a part file outside the installed skills.
    """
    file_path = PurePosixPath(path)
    if file_path.name == "SKILL.md":
        return file_path.parent.name
    key = f"{file_path.parent.name}/{file_path.name}"
    installed = installed_skill_file(key) if file_path.suffix == ".md" else None
    if installed is None:
        return None
    read = (Path(cwd) / Path(os.path.expandvars(path)).expanduser()).resolve()
    return key if read == installed.resolve() else None


def required_skill_for(command_names: list[str]) -> str | None:
    """Return the required skill name for a list of command names, if any.

    Args:
        command_names: The names of commands extracted from the shell input.

    Returns:
        The required skill name, or None if no requirement applies.
    """
    for name in command_names:
        if name in _SKILL_REQUIREMENTS:
            return _SKILL_REQUIREMENTS[name]
    return None


def _file_inputs(cmd: ParsedCommand) -> list[str]:
    """Return the files a file-reading command opens: its operands, less a sed/awk program, and stdin redirects."""
    operands: list[str] = []
    has_program_option = False
    skip_next = False
    runs_program = cmd.name in _PROGRAM_READERS
    for word in cmd.words:
        if skip_next:
            skip_next = False
        elif word.startswith("-"):
            is_program_option = runs_program and bool(_PROGRAM_OPTION.fullmatch(word))
            skip_next = is_program_option or (cmd.name == "awk" and bool(_AWK_VALUE_OPTION.fullmatch(word)))
            has_program_option |= is_program_option or (runs_program and bool(_ATTACHED_PROGRAM_OPTION.fullmatch(word)))
        else:
            operands.append(word)
    if runs_program and not has_program_option:
        operands = operands[1:]
    return [*operands, *cmd.redirect_inputs]


def skills_in_command(command: str) -> list[str]:
    """Return skill names and part keys referenced by skill file paths that a shell command reads.

    Args:
        command: The shell command string.

    Returns:
        Skill names and `<skill>/<part>.md` keys of skill files that file-reading commands (e.g. cat/sed) open.
    """
    if not command:
        return []
    import bashlex  # ruff: ignore[import-outside-top-level]
    import bashlex.errors  # ruff: ignore[import-outside-top-level]

    try:
        commands = extract_commands(bashlex.parse(command))
    except (bashlex.errors.ParsingError, NotImplementedError):
        return []
    session_cwd = str(Path.cwd())
    return [
        key
        for index, cmd in enumerate(commands)
        if cmd.name in _FILE_READERS
        for path in _file_inputs(cmd)
        if (key := skill_key(path, effective_cwd(commands, index, session_cwd)))
    ]


def reset(task_id: str) -> None:
    """Clear recorded skills for a task session, and every per-agent entry under it.

    Args:
        task_id: The session or task identifier.
    """
    discard_key(_STATE_PATH, task_id)
    discard_prefix(_STATE_PATH, f"{task_id}:")


def _is_skill_invocation(tool_name: str, parameters: dict[str, Any], skill_names: frozenset[str]) -> bool:
    """Check whether the current tool call invokes one of the given skills.

    Covers every way a skill loads: the Skill/use_skill tools, a Read of a
    SKILL.md file, or a shell command that reads a SKILL.md file.

    Args:
        tool_name: The tool name as reported by the frontend.
        parameters: The tool parameters.
        skill_names: The skill names to match against.

    Returns:
        True if the tool call invokes any of the given skills.
    """
    if tool_name == CanonicalTool.SKILL:
        return SkillParameters.build(parameters).skill in skill_names
    if tool_name == CanonicalTool.READ:
        path = ReadParameters.build(parameters).path
        return any(path.endswith(f"{name}/SKILL.md") for name in skill_names)
    if tool_name in SHELL_TOOLS:
        loaded = skills_in_command(str(ShellParameters.build(parameters).command))
        return any(name in loaded for name in skill_names)
    return False


def is_session_end_skill(tool_name: str, parameters: dict[str, object]) -> bool:
    """Check whether the current tool call is invoking the session-end skill.

    Args:
        tool_name: The tool name as reported by the frontend.
        parameters: The tool parameters.

    Returns:
        True if this is a session-end skill invocation.
    """
    return _is_skill_invocation(tool_name, parameters, frozenset({"session-end"}))


def is_wrap_up_skill(tool_name: str, parameters: dict[str, object]) -> bool:
    """Check whether the current tool call invokes a session wrap-up skill.

    Args:
        tool_name: The tool name as reported by the frontend.
        parameters: The tool parameters.

    Returns:
        True if this is a session-end or handoff skill invocation.
    """
    return _is_skill_invocation(tool_name, parameters, _WRAP_UP_SKILLS)
