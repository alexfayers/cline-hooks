from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from cline_hooks.core.plugin import HookResult, HooksPlugin, collect_contributions, hookspec, is_subagent
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.vocabulary import NO_RESET_TASK_START_SOURCES, CanonicalHook
from cline_hooks.state.skills import record_skill

if TYPE_CHECKING:
    from collections.abc import Callable
    import logging

RESERVE_CHARS = 3_000
NOTE_SEPARATOR = "\n\n"


@dataclass(frozen=True)
class StartupBlock:
    """Text injected at session start in place of a step the model would otherwise do.

    Attributes:
        title: What the block is, shown in its header.
        replaces: The step the block makes unnecessary.
        body: Builds the block text from the characters left, or None where there is no cap.
        skill: Skill name recorded as loaded when the block is injected, or empty.
        order: Lower values are injected first.
    """

    title: str
    replaces: str
    body: Callable[[int | None], str]
    skill: str = ""
    order: int = 100


def budget() -> int | None:
    """Return the characters startup blocks may use on the active frontend.

    Returns:
        The frontend's context cap less the reserve kept for other notes, or None where it has no cap.
    """
    spec = get_protocol().frontend_spec
    if spec is None or spec.max_context_chars is None:
        return None
    return spec.max_context_chars - RESERVE_CHARS


def block_text(block: StartupBlock, body: str) -> str:
    """Render a startup block around a body.

    Args:
        block: The block to render.
        body: The block's body text.

    Returns:
        The header, the step the block replaces, and the body.
    """
    replaced = f"Result of: {block.replaces}. Already done - do not repeat it."
    return f"Startup block: {block.title}\n{replaced}\n\n{body}"


def _render(block: StartupBlock, room: int | None, logger: logging.Logger) -> str | None:
    """Render a block within the room left, or None where it cannot be injected.

    Args:
        block: The block to render.
        room: The characters left for this note, or None where there is no cap.
        logger: The logger to report a failing body to.

    Returns:
        The block text, or None where there is no room for it or its body raised.
    """
    left = None if room is None else room - len(block_text(block, ""))
    if left is not None and left <= 0:
        return None
    try:
        text = block_text(block, block.body(left))
    except Exception:
        logger.exception("Startup block %r raised", block.title)
        return None
    return text if room is None or len(text) <= room else None


class StartupBlocksSpec:
    """Extension point for contributing startup blocks."""

    @hookspec
    def startup_blocks(self, workspace_roots: list[str]) -> list[StartupBlock]:
        """Return the startup blocks this plugin injects at session start.

        Args:
            workspace_roots: List of workspace root paths.

        Returns:
            The blocks to inject; empty to contribute nothing.
        """
        raise NotImplementedError


class StartupBlocksPlugin(HooksPlugin):
    """Owns startup blocks: text injected at session start in place of steps the model would do."""

    hookspecs = StartupBlocksSpec

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        """Inject the contributed startup blocks at a fresh TaskStart.

        Args:
            hook_name: The hook event name.
            logger: This plugin's hook-scoped child logger.
            **kwargs: Hook-specific keyword arguments.

        Returns:
            A HookResult carrying one note per block, or None if there are none.
        """
        if hook_name != CanonicalHook.TASK_START or kwargs.get("source") in NO_RESET_TASK_START_SOURCES:
            return None
        if is_subagent(kwargs):
            return None
        workspace_roots = cast("list[str]", kwargs.get("workspace_roots") or [])
        contributions = collect_contributions(StartupBlocksSpec.startup_blocks, list, workspace_roots=workspace_roots)
        blocks: list[StartupBlock] = []
        for item in (item for contribution in contributions for item in contribution):
            if isinstance(item, StartupBlock):
                blocks.append(item)
            else:
                logger.error("Dropped a startup block contribution of type %s", type(item).__name__)
        task_id = kwargs.get("task_id")
        cap = budget()
        notes: list[str] = []
        used = 0
        for block in sorted(blocks, key=lambda b: (b.order, b.title)):
            room = None if cap is None else cap - used - (len(NOTE_SEPARATOR) if notes else 0)
            note = _render(block, room, logger)
            if note is not None and block.skill and isinstance(task_id, str):
                record_skill(task_id, block.skill)
            note = note or f"{block.title} was not injected. Do this yourself: {block.replaces}."
            if room is not None and len(note) > room:
                logger.error("Dropped startup block %r: no room left for its fallback note", block.title)
                continue
            notes.append(note)
            used += len(note) + (len(NOTE_SEPARATOR) if len(notes) > 1 else 0)
        return HookResult(notes=notes) if notes else None
