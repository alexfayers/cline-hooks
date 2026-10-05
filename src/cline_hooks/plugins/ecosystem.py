from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import TYPE_CHECKING, cast

from cline_hooks.core.plugin import HookResult, HooksPlugin, collect_contributions, hookspec
from cline_hooks.core.vocabulary import CanonicalHook
from cline_hooks.state.workspace import record_workspace, should_note_workspace_change

if TYPE_CHECKING:
    import logging


@dataclass
class ToolingNote:
    """A plugin-supplied ecosystem tooling note.

    Attributes:
        note: The guidance text to show.
        replaces_generic: If True, suppress the generic ecosystem tooling
            note in favour of this one. If False, this note is shown
            alongside the generic note (or lack thereof).
    """

    note: str
    replaces_generic: bool = True


class EcosystemSpec:
    """Extension point for contributing ecosystem tooling notes."""

    @hookspec
    def ecosystem_tooling_note(self, workspace_roots: list[str]) -> ToolingNote | None:
        """Return this plugin's ecosystem tooling note for these workspace roots.

        Args:
            workspace_roots: List of workspace root paths.

        Returns:
            The note to show, or None to contribute nothing.
        """
        raise NotImplementedError


@dataclass(frozen=True)
class ToolingDetector:
    """One ecosystem's marker file, preferred tool, and guidance notes."""

    marker_file: str
    command: str
    note_with_tool: str
    note_without_tool: str


_DETECTORS: tuple[ToolingDetector, ...] = (
    ToolingDetector(
        marker_file="pyproject.toml",
        command="uv",
        note_with_tool=(
            "This is a Python project (pyproject.toml). SHOULD use `uv run`/`uv add`, not pip/python directly."
        ),
        note_without_tool="This is a Python project (pyproject.toml).",
    ),
    # Future ecosystems (not implemented yet): TypeScript (package.json / pnpm), Rust (Cargo.toml / cargo).
)


def _generic_tooling_note(workspace_roots: list[str]) -> str | None:
    """Return ecosystem tooling guidance for the first matching root/detector.

    Args:
        workspace_roots: List of workspace root paths to search.

    Returns:
        A note recommending the ecosystem's preferred tool (if installed) or
        just naming the ecosystem (if not); None if no root/detector matches.
    """
    for root in workspace_roots:
        for detector in _DETECTORS:
            if not (Path(root) / detector.marker_file).exists():
                continue
            if shutil.which(detector.command):
                return detector.note_with_tool
            return detector.note_without_tool
    return None


def resolve_tooling_notes(workspace_roots: list[str]) -> list[str]:
    """Merge contributed tooling notes with the generic ecosystem note.

    Args:
        workspace_roots: List of workspace root paths to search.

    Returns:
        Ordered notes: the generic note (unless a contributor replaces it), then
        replacing contributor notes, then additive contributor notes.
    """
    contributions = collect_contributions(
        EcosystemSpec.ecosystem_tooling_note, ToolingNote, workspace_roots=workspace_roots
    )
    replacing = [c.note for c in contributions if c.replaces_generic]
    additive = [c.note for c in contributions if not c.replaces_generic]
    generic = None if replacing else _generic_tooling_note(workspace_roots)
    return [*([generic] if generic else []), *replacing, *additive]


class EcosystemPlugin(HooksPlugin):
    """Owns ecosystem tooling notes and the working-directory reminder."""

    hookspecs = EcosystemSpec

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Surface tooling notes at TaskStart/TaskResume and after a working-directory change.

        Args:
            hook_name: The hook event name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult carrying the tooling notes, or None if there are none to show.
        """
        task_id = cast("str", kwargs["task_id"])
        workspace_roots = cast("list[str]", kwargs.get("workspace_roots") or [])
        if hook_name in {CanonicalHook.TASK_START, CanonicalHook.TASK_RESUME}:
            record_workspace(task_id, workspace_roots)
            notes = resolve_tooling_notes(workspace_roots)
            return HookResult(notes=notes) if notes else None
        if hook_name == CanonicalHook.POST_TOOL_USE and should_note_workspace_change(task_id, workspace_roots):
            notes = resolve_tooling_notes(workspace_roots)
            if notes:
                return HookResult(notes=[f"Working directory changed to {workspace_roots[0]}. " + "\n\n".join(notes)])
        return None
