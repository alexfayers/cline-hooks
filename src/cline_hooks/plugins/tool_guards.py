from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from cline_hooks.core.parameters import (
    FileEditParameters,
    PlanModeRespondParameters,
    ReadParameters,
)
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool, PluginScope
from cline_hooks.handlers.commands import contains_comment, extract_replacement_blocks
from cline_hooks.handlers.git_context import get_dirty_count

if TYPE_CHECKING:
    import logging

_LARGE_FILE_THRESHOLD = 1000
_EMOJI_THRESHOLD = 0x7F


def _starts_with_emoji(text: str) -> bool:
    """Check if text starts with a non-ASCII character (emoji canary).

    Args:
        text: The text to check.

    Returns:
        True if the first non-whitespace character is non-ASCII.
    """
    stripped = text.lstrip()
    return bool(stripped) and ord(stripped[0]) > _EMOJI_THRESHOLD


def _reads_bounded_range(params: ReadParameters) -> bool:
    """Check whether a read asks for a line range within the large-file threshold.

    Args:
        params: The read call's parameters.

    Returns:
        True if the call names an end line within a threshold-sized span.
    """
    if params.end_line is None:
        return False
    return params.end_line - (params.start_line or 0) <= _LARGE_FILE_THRESHOLD


def _plan_mode_respond_guard(logger: logging.Logger, parameters: dict[str, Any]) -> HookResult | None:
    """Block a plan-mode response that doesn't start with the emoji canary.

    Args:
        logger: This plugin's hook-scoped child logger.
        parameters: The plan_mode_respond call's parameters.

    Returns:
        A blocking HookResult if the response is missing the emoji canary.
    """
    response = PlanModeRespondParameters.build(parameters).response
    if _starts_with_emoji(response):
        return None
    spawn_tool = get_protocol().native_tool_name(CanonicalTool.SPAWN_AGENT)
    logger.debug("Blocked plan-mode response: missing emoji canary")
    return HookResult(
        block=(
            "Response does not start with an emoji - context window may be degraded. "
            f"MUST use the {spawn_tool} tool to start a fresh context."
        )
    )


def _read_guard(logger: logging.Logger, parameters: dict[str, Any]) -> HookResult | None:
    """Block reading a file that's too large to read in full.

    Args:
        logger: This plugin's hook-scoped child logger.
        parameters: The read call's parameters.

    Returns:
        A blocking HookResult if the file exceeds the large-file threshold and
        the call asks for more of it than the threshold allows.
    """
    params = ReadParameters.build(parameters)
    if not params.path or _reads_bounded_range(params):
        return None
    try:
        line_count = Path(params.path).read_text(encoding="utf-8", errors="replace").count("\n")
    except OSError:
        return None
    if line_count > _LARGE_FILE_THRESHOLD:
        logger.debug("Blocked read: file exceeds large-file threshold")
        return HookResult(
            block=(
                f"{params.path} is {line_count} lines. "
                "MUST search it with specific patterns instead of reading the whole file."
            )
        )
    return None


def _file_edit_comment_guard(logger: logging.Logger, parameters: dict[str, Any]) -> HookResult | None:
    """Flag disallowed explanatory comments and bare type-ignore comments.

    Args:
        logger: This plugin's hook-scoped child logger.
        parameters: The file-edit call's parameters.

    Returns:
        A HookResult carrying comment/type-ignore notes, or None.
    """
    diff = FileEditParameters.build(parameters).diff
    if not diff:
        return None

    notes: set[str] = set()

    for replacement_block in extract_replacement_blocks(diff):
        for line in replacement_block.split("\n"):
            if (stripped_line := line.strip()) and contains_comment(line):
                if "# type: ignore" in stripped_line and "ignore[" not in stripped_line:
                    notes.add("SHOULD NOT use type ignore comments; where necessary, MUST use a specific ignore.")
                else:
                    notes.add(
                        "MUST NOT write comments explaining the reasoning for a specific change. "
                        "Comments SHOULD only be used to explain complex code. If comments are "
                        "required, consider a different approach."
                    )

    if not notes:
        return None
    logger.debug("Flagged disallowed comment(s) in file edit")
    return HookResult(notes=list(notes))


def _pre_tool_use_guard(logger: logging.Logger, **kwargs: object) -> HookResult | None:
    """Guard a PreToolUse call based on its tool name.

    Args:
        logger: This plugin's hook-scoped child logger.
        **kwargs: The PreToolUse dispatch kwargs (tool_name, parameters, ...).

    Returns:
        A HookResult with a block reason or notes, or None.
    """
    tool_name = kwargs.get("tool_name")
    parameters = cast("dict[str, Any]", kwargs.get("parameters") or {})
    if tool_name == CanonicalTool.PLAN_MODE_RESPOND:
        return _plan_mode_respond_guard(logger, parameters)
    if tool_name == CanonicalTool.READ:
        return _read_guard(logger, parameters)
    if tool_name in {CanonicalTool.EDIT, CanonicalTool.WRITE}:
        return _file_edit_comment_guard(logger, parameters)
    return None


def _attempt_completion_guard(logger: logging.Logger, **kwargs: object) -> HookResult | None:
    """Block finishing with incomplete task_progress items or a dirty working tree.

    Args:
        logger: This plugin's hook-scoped child logger.
        **kwargs: The AttemptCompletion dispatch kwargs (task_progress, workspace_roots).

    Returns:
        A blocking HookResult for incomplete task_progress or a dirty repo.
    """
    task_progress = cast("str", kwargs.get("task_progress") or "")
    incomplete = [line for line in task_progress.splitlines() if line.strip().startswith("- [ ]")]
    if incomplete:
        logger.debug("Blocked completion: task_progress has incomplete item(s)")
        return HookResult(
            block=f"task_progress has {len(incomplete)} incomplete item(s). MUST complete them before finishing."
        )
    workspace_roots = cast("list[str]", kwargs.get("workspace_roots") or [])
    if get_dirty_count(workspace_roots):
        logger.debug("Blocked completion: working directory has uncommitted changes")
        return HookResult(block="Working directory has uncommitted changes")
    return None


class ToolGuardsPlugin(HooksPlugin):
    """Bundled plugin enforcing per-tool PreToolUse and attempt-completion guards."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Dispatch PreToolUse and AttemptCompletion events to their guards.

        Args:
            hook_name: The hook or plugin-scope name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult with a block reason or notes, or None.
        """
        if hook_name == CanonicalHook.PRE_TOOL_USE:
            return _pre_tool_use_guard(logger, **kwargs)
        if hook_name == PluginScope.ATTEMPT_COMPLETION:
            return _attempt_completion_guard(logger, **kwargs)
        return None
