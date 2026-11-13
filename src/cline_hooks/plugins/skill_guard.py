from __future__ import annotations

import os
from pathlib import Path
import re
from typing import TYPE_CHECKING, cast

from cline_hooks.core.hook_kwargs import PreToolUseKwargs
from cline_hooks.core.parameters import FileEditParameters
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool, PluginScope
from cline_hooks.handlers.commands import ParsedCommand, extract_commands, is_read_only_git, is_tidy_rebase
from cline_hooks.state.skills import _SKILL_REQUIREMENTS, installed_skill_file, is_skill_called, required_skill_for

if TYPE_CHECKING:
    from collections.abc import Callable
    import logging


_SETUP_PART = "llm-prompts/setup.md"


def _is_llm_prompts_setup(cmd: ParsedCommand) -> bool:
    """Return True if a command runs `llm-prompts setup` or `llm-prompts install`."""
    return cmd.name == "llm-prompts" and cmd.args[:1] in (["setup"], ["install"])


def _is_contribute_write(cmd: ParsedCommand) -> bool:
    """Return True if a command runs `llm-prompts contribute sync` or `llm-prompts contribute update`."""
    return cmd.name == "llm-prompts" and cmd.args[:2] in (["contribute", "sync"], ["contribute", "update"])


_SHELL_PART_REQUIREMENTS: tuple[tuple[Callable[[ParsedCommand], bool], str], ...] = (
    (is_tidy_rebase, "git-usage/tidy.md"),
    (_is_llm_prompts_setup, _SETUP_PART),
    (_is_contribute_write, "llm-prompts/contribute.md"),
)
_EDIT_PART_REQUIREMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?:^|/)prompts/[\w-]+/(?:rules|skills|workflows|agents)/"), "llm-prompts/edit.md"),
    (re.compile(r"(?:^|/)llm-prompts/config\.toml$"), _SETUP_PART),
)
_GUARDED_KEYS = frozenset({
    *_SKILL_REQUIREMENTS.values(),
    *(part for _, part in _SHELL_PART_REQUIREMENTS),
    *(part for _, part in _EDIT_PART_REQUIREMENTS),
})


def _missing(task_id: str, skill: str | None, parts: list[str]) -> list[str]:
    """Return the required skill and installed parts not yet read, in order."""
    keys = [*([skill] if skill else []), *(part for part in parts if installed_skill_file(part))]
    return [key for key in dict.fromkeys(keys) if not is_skill_called(task_id, key)]


def _block_message(keys: list[str], action: str) -> str:
    """Return the block naming each missing skill or part, and its installed file."""
    labels = " and ".join(f"the `{key}` skill part" if "/" in key else f"the `{key}` skill" for key in keys)
    message = f"MUST use {labels} before {action}"
    files = [str(file) for key in keys if (file := installed_skill_file(key))]
    return f"{message} - read {' and '.join(files)} first" if files else message


def _pre_shell_guard(logger: logging.Logger, **kwargs: object) -> HookResult | None:
    """Block a shell command missing a required skill or skill part.

    Args:
        logger: This plugin's hook-scoped child logger.
        **kwargs: The PreShell dispatch kwargs (command, task_id).

    Returns:
        A blocking HookResult for a missing skill or part, or None.
    """
    command = cast("str", kwargs.get("command") or "")
    task_id = cast("str", kwargs.get("task_id") or "")

    import bashlex.errors  # ruff: ignore[import-outside-top-level]

    try:
        parsed = bashlex.parse(command)
    except (bashlex.errors.ParsingError, NotImplementedError):
        return None
    commands = extract_commands(parsed)

    skill = required_skill_for([cmd.name for cmd in commands if not is_read_only_git(cmd)])
    parts = [part for matches, part in _SHELL_PART_REQUIREMENTS for cmd in commands if matches(cmd)]
    missing = _missing(task_id, skill, parts)
    if missing:
        logger.debug("Blocked shell command: missing required skill or part")
        return HookResult(block=_block_message(missing, "running this command"))
    return None


def _pre_edit_guard(logger: logging.Logger, **kwargs: object) -> HookResult | None:
    """Block an edit or write to a prompt source or llm-prompts config before its skill part was read.

    Args:
        logger: This plugin's hook-scoped child logger.
        **kwargs: The PreToolUse dispatch kwargs (tool_name, parameters, task_id, workspace_roots).

    Returns:
        A blocking HookResult for a missing skill part, or None.
    """
    kw = PreToolUseKwargs.build(kwargs)
    if kw.tool_name not in {CanonicalTool.EDIT, CanonicalTool.WRITE}:
        return None
    path = FileEditParameters.build(kw.parameters).path
    if not isinstance(path, str) or not path:
        return None
    base = kw.workspace_roots[0] if kw.workspace_roots else os.getcwd()  # ruff: ignore[os-getcwd]
    resolved = os.path.normpath(Path(base) / Path(path).expanduser())
    parts = [part for pattern, part in _EDIT_PART_REQUIREMENTS if pattern.search(resolved)]
    missing = _missing(kw.task_id, None, parts)
    if missing:
        logger.debug("Blocked edit: missing required skill part")
        return HookResult(block=_block_message(missing, f"editing {path}"))
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
    pending_skills = {key for reason in block_reasons for key in _GUARDED_KEYS if f"`{key}`" in reason}
    if not pending_skills:
        return None
    skills_list = ", ".join(f"`{s}`" for s in sorted(pending_skills))
    logger.debug("Re-nudged pending skill requirement(s) on task resume")
    return HookResult(notes=[f"REQUIRED: use the {skills_list} skill(s) before retrying the blocked command."])


class SkillGuardPlugin(HooksPlugin):
    """Bundled plugin blocking commands and edits until their required skill or skill part was read."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Dispatch PreShell, PreToolUse and TaskResume events to the skill guards.

        Args:
            hook_name: The hook or plugin-scope name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult with a block reason or notes, or None.
        """
        if hook_name == PluginScope.PRE_SHELL:
            return _pre_shell_guard(logger, **kwargs)
        if hook_name == CanonicalHook.PRE_TOOL_USE:
            return _pre_edit_guard(logger, **kwargs)
        if hook_name == CanonicalHook.TASK_RESUME:
            return _task_resume_guard(logger, **kwargs)
        return None
