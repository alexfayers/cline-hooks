from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from cline_hooks.core.hook_kwargs import PreToolUseKwargs
from cline_hooks.core.parameters import FileEditParameters
from cline_hooks.core.plugin import HookResult, HooksPlugin
from cline_hooks.core.vocabulary import FILE_EDIT_TOOLS, CanonicalHook

if TYPE_CHECKING:
    import logging

MAX_FILES_PER_FOLDER = 8


def _file_count(folder: Path) -> int:
    """Count the regular files directly in a folder, including dotfiles and file symlinks.

    Args:
        folder: The folder to count in.

    Returns:
        The number of immediate non-directory entries.
    """
    return sum(not entry.is_dir() for entry in folder.iterdir())


def _reaches_limit_with(path: Path) -> bool:
    """Check whether creating a path would bring its folder, other than a repo root, exactly to the file limit.

    Args:
        path: The file about to be created.

    Returns:
        True for a new file in an existing non-root folder that would then hold exactly the limit of files.
    """
    return (
        not path.exists()
        and path.parent.is_dir()
        and not (path.parent / ".git").exists()
        and _file_count(path.parent) + 1 == MAX_FILES_PER_FOLDER
    )


def _crowding_result(logger: logging.Logger, kwargs: PreToolUseKwargs) -> HookResult | None:
    """Note a new file that brings its folder to the file limit.

    Args:
        logger: This plugin's hook-scoped child logger.
        kwargs: The PreToolUse call's typed kwargs.

    Returns:
        A note-carrying HookResult for the file that reaches the limit, else None.
    """
    raw: object = FileEditParameters.build(kwargs.parameters or {}).path
    if not isinstance(raw, str) or not raw:
        return None
    roots = kwargs.workspace_roots or []
    path = Path(raw)
    if not path.is_absolute():
        if len(roots) > 1:
            return None
        path = Path(roots[0] if roots else Path.cwd()) / path
    try:
        reaches_limit = _reaches_limit_with(path)
    except OSError:
        logger.exception("Could not inspect the folder of %s", path)
        return None
    if not reaches_limit:
        return None
    logger.debug("Noted new file: folder would hold %d files", MAX_FILES_PER_FOLDER)
    return HookResult(
        notes=[
            (
                f"This new file brings its folder to {MAX_FILES_PER_FOLDER} files. "
                "MUST put new related files in a short-named area subfolder. "
                "MUST NOT move existing files."
            )
        ]
    )


class FileStructurePlugin(HooksPlugin):
    """Bundled plugin noting a new file that brings its folder to eight files."""

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Return the file-structure result for a PreToolUse file creation, else None.

        Args:
            hook_name: The hook or plugin-scope name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A note-carrying HookResult, or None.
        """
        if hook_name != CanonicalHook.PRE_TOOL_USE:
            return None
        tool_kwargs = PreToolUseKwargs.build(kwargs)
        if tool_kwargs.tool_name not in FILE_EDIT_TOOLS:
            return None
        return _crowding_result(logger, tool_kwargs)
