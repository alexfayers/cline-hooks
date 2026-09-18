from __future__ import annotations

import json
import logging
import re
from typing import Any

from cline_hooks.core.parameters import ReadParameters, ShellParameters, SkillParameters
from cline_hooks.core.vocabulary import SHELL_TOOLS, CanonicalTool
from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks.state.skills")

_SKILL_REQUIREMENTS: dict[str, str] = {
    "git": "git-usage",
    "cr": "cr",
}

_SKILL_MD_PATH = re.compile(r"([\w.-]+)/SKILL\.md\b")

_WRAP_UP_SKILLS = frozenset({"session-end", "handoff"})

_STATE_PATH = get_data_dir() / "skill-state.json"


def _read() -> dict[str, list[str]]:
    try:
        return dict(json.loads(_STATE_PATH.read_text()))
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def _write(data: dict[str, list[str]]) -> None:
    _STATE_PATH.write_text(json.dumps(data))


def record_skill(task_id: str, skill_name: str) -> None:
    """Record that a skill has been called for a task.

    Args:
        task_id: The session or task identifier.
        skill_name: The name of the skill that was called.
    """
    data = _read()
    skills = set(data.get(task_id, []))
    skills.add(skill_name)
    data[task_id] = sorted(skills)
    _write(data)


def is_skill_called(task_id: str, skill_name: str) -> bool:
    """Check whether a skill has been called for a task.

    Args:
        task_id: The session or task identifier.
        skill_name: The skill name to check.

    Returns:
        True if the skill has been called for the task.
    """
    return skill_name in _read().get(task_id, [])


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


def skills_in_command(command: str) -> list[str]:
    """Return skill names referenced by SKILL.md paths inside a shell command.

    Args:
        command: The shell command string.

    Returns:
        Skill names whose SKILL.md is read by the command (e.g. via cat/sed).
    """
    return _SKILL_MD_PATH.findall(command)


def reset(task_id: str) -> None:
    """Clear recorded skills for a task session.

    Args:
        task_id: The session or task identifier.
    """
    data = _read()
    if task_id in data:
        del data[task_id]
        _write(data)


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
