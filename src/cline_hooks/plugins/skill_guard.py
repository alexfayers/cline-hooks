from __future__ import annotations

import os
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any, cast

from cline_hooks.core.hook_kwargs import PreToolUseKwargs
from cline_hooks.core.parameters import FileEditParameters, ShellParameters
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.vocabulary import SHELL_TOOLS, CanonicalHook, CanonicalTool, PluginScope
from cline_hooks.handlers.commands import (
    ParsedCommand,
    extract_commands,
    is_read_only_git,
    is_tidy_rebase,
    parse_command,
)
from cline_hooks.state.skills import (
    _SKILL_REQUIREMENTS,
    installed_skill_file,
    is_skill_called,
    record_skill,
    required_skill_for,
)

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


def _with_skill_text(keys: list[str], action: str) -> HookResult:
    """Return the call allowed with the installed text of each missing skill.

    A key without an installed file has no text to add, so the call is blocked instead.
    """
    files = {key: installed_skill_file(key) for key in keys}
    if not all(files.values()):
        return HookResult(block=_block_message(keys, action))
    return HookResult(
        notes=[f"REQUIRED: the `{key}` skill:\n\n{file.read_text()}" for key, file in files.items() if file]
    )


def _missing_for_command(command: str, task_id: str) -> list[str]:
    """Return the skills and parts a shell command requires and the task has not read."""
    if not command:
        return []
    import bashlex.errors  # ruff: ignore[import-outside-top-level]

    try:
        parsed = parse_command(command)
    except (bashlex.errors.ParsingError, NotImplementedError):
        return []
    commands = extract_commands(parsed)

    skill = required_skill_for([cmd.name for cmd in commands if not is_read_only_git(cmd)])
    parts = [part for matches, part in _SHELL_PART_REQUIREMENTS for cmd in commands if matches(cmd)]
    return _missing(task_id, skill, parts)


def _missing_for_edit(
    tool_name: str, parameters: dict[str, Any], workspace_roots: list[str], task_id: str
) -> tuple[list[str], str]:
    """Return the skill parts an edit or write requires and the task has not read, and the path edited."""
    if tool_name not in {CanonicalTool.EDIT, CanonicalTool.WRITE}:
        return [], ""
    path = FileEditParameters.build(parameters).path
    if not isinstance(path, str) or not path:
        return [], ""
    base = workspace_roots[0] if workspace_roots else os.getcwd()  # ruff: ignore[os-getcwd]
    resolved = os.path.normpath(Path(base) / Path(path).expanduser())
    parts = [part for pattern, part in _EDIT_PART_REQUIREMENTS if pattern.search(resolved)]
    return _missing(task_id, None, parts), path


def _pre_shell_guard(logger: logging.Logger, **kwargs: object) -> HookResult | None:
    """Add the text of a skill or skill part a shell command requires and has not read.

    Args:
        logger: This plugin's hook-scoped child logger.
        **kwargs: The PreShell dispatch kwargs (command, task_id).

    Returns:
        A HookResult carrying the missing skill text, blocking where a skill is not installed, or None.
    """
    missing = _missing_for_command(cast("str", kwargs.get("command") or ""), cast("str", kwargs.get("task_id") or ""))
    if not missing:
        return None
    logger.debug("Adding missing required skill or part to shell command")
    return _with_skill_text(missing, "running this command")


def _pre_edit_guard(logger: logging.Logger, **kwargs: object) -> HookResult | None:
    """Add the skill part text an edit or write to a prompt source or llm-prompts config requires.

    Args:
        logger: This plugin's hook-scoped child logger.
        **kwargs: The PreToolUse dispatch kwargs (tool_name, parameters, task_id, workspace_roots).

    Returns:
        A HookResult carrying the missing skill part text, or None.
    """
    kw = PreToolUseKwargs.build(kwargs)
    missing, path = _missing_for_edit(kw.tool_name, kw.parameters, kw.workspace_roots, kw.task_id)
    if not missing:
        return None
    logger.debug("Adding missing required skill part to edit")
    return _with_skill_text(missing, f"editing {path}")


def _delivered_guard(**kwargs: object) -> None:
    """Record the skills the allowed call's response carried, so a retry does not add them again.

    Args:
        **kwargs: The ToolAllowed dispatch kwargs (tool_name, parameters, task_id, workspace_roots).
    """
    kw = PreToolUseKwargs.build(kwargs)
    if kw.tool_name in SHELL_TOOLS:
        missing = _missing_for_command(ShellParameters.build(kw.parameters).command, kw.task_id)
    else:
        missing, _ = _missing_for_edit(kw.tool_name, kw.parameters, kw.workspace_roots, kw.task_id)
    for key in missing:
        record_skill(kw.task_id, key)


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
    """Bundled plugin adding the skill or skill part text a command or edit requires, once per session."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Dispatch PreShell, PreToolUse, ToolAllowed and TaskResume events to the skill guards.

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
        if hook_name == PluginScope.TOOL_ALLOWED:
            _delivered_guard(**kwargs)
            return None
        if hook_name == CanonicalHook.TASK_RESUME:
            return _task_resume_guard(logger, **kwargs)
        return None
