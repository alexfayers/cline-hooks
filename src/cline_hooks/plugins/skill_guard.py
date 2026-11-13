from __future__ import annotations

from typing import TYPE_CHECKING, cast

from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.vocabulary import CanonicalHook, PluginScope
from cline_hooks.handlers.commands import extract_commands, is_read_only_git
from cline_hooks.state.skills import _SKILL_REQUIREMENTS, is_skill_called, required_skill_for

if TYPE_CHECKING:
    import logging


def _skill_block_message(skill: str) -> str:
    message = f"MUST use the `{skill}` skill before running this command"
    spec = get_protocol().frontend_spec
    if spec is not None and spec.skills_dir is not None:
        skill_file = spec.skills_dir() / skill / "SKILL.md"
        if skill_file.is_file():
            return f"{message} - read {skill_file} first"
    return message


def _pre_shell_guard(logger: logging.Logger, **kwargs: object) -> HookResult | None:
    """Block a shell command missing a required skill.

    Args:
        logger: This plugin's hook-scoped child logger.
        **kwargs: The PreShell dispatch kwargs (command, task_id).

    Returns:
        A blocking HookResult for a missing skill, or None.
    """
    command = cast("str", kwargs.get("command") or "")
    task_id = cast("str", kwargs.get("task_id") or "")

    import bashlex.errors  # ruff: ignore[import-outside-top-level]

    try:
        parsed = bashlex.parse(command)
    except (bashlex.errors.ParsingError, NotImplementedError):
        return None
    commands = extract_commands(parsed)

    required_skill = required_skill_for([cmd.name for cmd in commands if not is_read_only_git(cmd)])
    if required_skill and not is_skill_called(task_id, required_skill):
        logger.debug("Blocked shell command: missing required skill")
        return HookResult(block=_skill_block_message(required_skill))
    return None


def _task_resume_guard(logger: logging.Logger, **kwargs: object) -> HookResult | None:
    """Re-nudge any skill named in this task's recorded block reasons.

    Args:
        logger: This plugin's hook-scoped child logger.
        **kwargs: The TaskResume dispatch kwargs (block_reasons, ...).

    Returns:
        A HookResult carrying the re-nudge note, or None if nothing pends.
    """
    block_reasons = cast("list[str]", kwargs.get("block_reasons") or [])
    pending_skills = {skill for reason in block_reasons for skill in _SKILL_REQUIREMENTS.values() if skill in reason}
    if not pending_skills:
        return None
    skills_list = ", ".join(f"`{s}`" for s in sorted(pending_skills))
    logger.debug("Re-nudged pending skill requirement(s) on task resume")
    return HookResult(notes=[f"REQUIRED: use the {skills_list} skill(s) before retrying the blocked command."])


class SkillGuardPlugin(HooksPlugin):
    """Bundled plugin blocking commands until their required skill was read."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Dispatch PreShell and TaskResume events to the skill guards.

        Args:
            hook_name: The hook or plugin-scope name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult with a block reason or notes, or None.
        """
        if hook_name == PluginScope.PRE_SHELL:
            return _pre_shell_guard(logger, **kwargs)
        if hook_name == CanonicalHook.TASK_RESUME:
            return _task_resume_guard(logger, **kwargs)
        return None
