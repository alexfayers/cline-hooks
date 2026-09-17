from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from cline_hooks.core.parameters import FileEditParameters
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool

if TYPE_CHECKING:
    import logging

try:
    from llm_prompts.install import (
        get_managed_files as _get_managed_files_impl,
        get_source_for_managed_file as _get_source_impl,
    )
except ImportError:
    _get_managed_files_impl = None
    _get_source_impl = None

_managed_files: set[str] | None = None


def _get_managed_files() -> set[str]:
    """Return cached set of managed file paths from the manifest."""
    global _managed_files  # ruff: ignore[global-statement]
    if _managed_files is None:
        if _get_managed_files_impl is not None:
            _managed_files = _get_managed_files_impl()
        else:
            _managed_files = set()
    return _managed_files


def _is_managed_path(path: str) -> bool:
    """Check if a file path is tracked in the llm-prompts manifest.

    Args:
        path: The file path to check.

    Returns:
        True if the file is managed by llm-prompts.
    """
    try:
        resolved = str(Path(path).resolve())
    except (OSError, ValueError):
        return False
    managed = _get_managed_files()
    if resolved in managed:
        return True
    return any(resolved.startswith(managed_path + "/") for managed_path in managed)


def _managed_source_instruction(path: str) -> str:
    """Return the edit instruction for a managed path, naming its source file.

    Args:
        path: The managed destination path.

    Returns:
        Instruction naming the resolved source file, or a generic instruction
        where the source cannot be resolved.
    """
    if _get_source_impl is not None:
        source = None
        with contextlib.suppress(Exception):
            source = _get_source_impl(path)
        if source:
            return f"MUST edit the source file {source} instead"
    return "MUST edit the source file instead"


def _pre_tool_use_guard(**kwargs: object) -> HookResult | None:
    """Block a PreToolUse edit or write to a managed file.

    Args:
        **kwargs: The PreToolUse dispatch kwargs (tool_name, parameters, ...).

    Returns:
        A blocking HookResult for a managed-file edit, or None.
    """
    tool_name = kwargs.get("tool_name")
    if tool_name not in {CanonicalTool.EDIT, CanonicalTool.WRITE}:
        return None
    parameters = cast("dict[str, Any]", kwargs.get("parameters") or {})
    file_path = FileEditParameters.build(parameters).path
    if not file_path or not _is_managed_path(file_path):
        return None
    return HookResult(
        block=(
            f"{file_path} is managed by llm-prompts. "
            f"{_managed_source_instruction(file_path)}, "
            "then run `llm-prompts update`."
        )
    )


class ManagedFilesPlugin(HooksPlugin):
    """Bundled plugin blocking edits to llm-prompts-managed files."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Dispatch PreToolUse events to the managed-file guard.

        Args:
            hook_name: The hook or plugin-scope name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult with a block reason, or None.
        """
        if hook_name == CanonicalHook.PRE_TOOL_USE:
            result = _pre_tool_use_guard(**kwargs)
            if result is not None:
                logger.debug("Blocked edit/write to a managed file")
            return result
        return None
