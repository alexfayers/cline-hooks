from __future__ import annotations

import json
import logging

from cline_hooks.paths import get_data_dir

logger = logging.getLogger("hooks")

_SKILL_REQUIREMENTS: dict[str, str] = {
    "git": "git-usage",
    "cr": "cr",
}

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
        task_id: The Cline task identifier.
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
        task_id: The Cline task identifier.
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


def reset(task_id: str) -> None:
    """Clear recorded skills for a task session.

    Args:
        task_id: The Cline task identifier.
    """
    data = _read()
    if task_id in data:
        del data[task_id]
        _write(data)
