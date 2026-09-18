from __future__ import annotations

from typing import TYPE_CHECKING, cast

import bashlex
import bashlex.errors

from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.vocabulary import CanonicalHook, PluginScope
from cline_hooks.handlers.commands import extract_commands, is_git_push
from cline_hooks.handlers.push_guard import marker_above_repo
from cline_hooks.state.skills import (
    _SKILL_REQUIREMENTS,
    is_skill_called,
    required_skill_for,
)

if TYPE_CHECKING:
    import logging


def _pre_shell_guard(logger: logging.Logger, **kwargs: object) -> HookResult | None:
    """Block a shell command missing a required skill or a blocked git push.

    Args:
        logger: This plugin's hook-scoped child logger.
        **kwargs: The PreShell dispatch kwargs (command, task_id, workspace_roots).

    Returns:
        A blocking HookResult for a missing skill or a blocked git push, or None.
    """
    command = cast("str", kwargs.get("command") or "")
    task_id = cast("str", kwargs.get("task_id") or "")
    workspace_roots = cast("list[str]", kwargs.get("workspace_roots") or [])

    try:
        parsed = bashlex.parse(command)
    except bashlex.errors.ParsingError:
        return None
    commands = extract_commands(parsed)

    required_skill = required_skill_for([cmd.name for cmd in commands])
    if required_skill and not is_skill_called(task_id, required_skill):
        logger.debug("Blocked shell command: missing required skill")
        return HookResult(block=f"MUST use the `{required_skill}` skill before running this command")

    if is_git_push(commands):
        marker = marker_above_repo(workspace_roots)
        if marker:
            logger.debug("Blocked git push: repo is inside a managed workspace")
            return HookResult(
                block=(
                    f"git push is blocked here: this repository is inside a managed "
                    f"workspace (a '{marker}' entry was found at or above the repo root). "
                    f"MUST use the workspace's own review/submit workflow instead of "
                    f"pushing directly."
                )
            )
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


class ShellGuardsPlugin(HooksPlugin):
    """Bundled plugin enforcing shell-command guards."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Dispatch PreShell and TaskResume events to the shell-command guards.

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
