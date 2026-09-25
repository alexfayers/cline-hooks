from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import logging
from typing import TYPE_CHECKING, Any

from cline_hooks.config import config_dir
from cline_hooks.core.install import resolve_binary
from cline_hooks.core.outcome import Outcome
from cline_hooks.core.plugin import collect_hook_results, load_plugins
from cline_hooks.core.protocol import get_protocol
from cline_hooks.core.registry import hook_handler
from cline_hooks.core.vocabulary import NO_RESET_TASK_START_SOURCES, CanonicalHook
from cline_hooks.daemon import lifecycle as daemon_lifecycle
from cline_hooks.daemon.server import package_version
from cline_hooks.frontends.claude_code.install import ClaudeCodeInstaller
from cline_hooks.frontends.claude_code.protocol import ClaudeCodeProtocol
from cline_hooks.handlers.git_context import resolve_tooling_notes
from cline_hooks.state.agents import reset as _reset_agents
from cline_hooks.state.memory import reset as _reset_memory
from cline_hooks.state.skills import reset as _reset_skills
from cline_hooks.state.store import TaskStateStore
from cline_hooks.state.workspace import (
    record_workspace,
    reset as reset_workspace,
)

if TYPE_CHECKING:
    from pathlib import Path

    from cline_hooks.core.models import (
        HookInputTaskCancel,
        HookInputTaskComplete,
        HookInputTaskResume,
        HookInputTaskStart,
    )
    from cline_hooks.state.store import TaskBlockEvent

logger = logging.getLogger("hooks.task_lifecycle")

_store = TaskStateStore()

_INSTALL_STAMP_PATH = config_dir() / "install-check.json"


@dataclass(frozen=True, slots=True)
class _InstallStamp:
    """A cached "already checked this version" marker for the install self-heal."""

    version: str
    entries_hash: str


def _claude_code_entries(binary: Path) -> dict[str, dict[str, Any]]:
    """Return the settings.json entry cline-hooks currently wants for each claude-code hook.

    Returns:
        A mapping of native hook event name to its desired entry.
    """
    installer = ClaudeCodeInstaller()
    return {
        registration.native_name: installer.build_entry(installer.entry_binary(registration, binary), registration)
        for registration in ClaudeCodeProtocol.supported_hooks.values()
    }


def _entries_hash(entries: dict[str, dict[str, Any]]) -> str:
    """Return a stable hash of a desired-entries mapping, for the stamp file.

    Returns:
        A hex digest over the entries' canonical JSON form.
    """
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode("utf-8")).hexdigest()


def _read_install_stamp() -> _InstallStamp | None:
    """Return the last-checked version/hash stamp, if the stamp file is present and valid.

    Returns:
        The stamp, or None if absent, unreadable, or malformed.
    """
    try:
        raw = json.loads(_INSTALL_STAMP_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    version, entries_hash = raw.get("version"), raw.get("hash")
    if not isinstance(version, str) or not isinstance(entries_hash, str):
        return None
    return _InstallStamp(version, entries_hash)


def _write_install_stamp(stamp: _InstallStamp) -> None:
    """Persist the version/hash stamp so the next SessionStart can skip the real check."""
    _INSTALL_STAMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    _INSTALL_STAMP_PATH.write_text(json.dumps({"version": stamp.version, "hash": stamp.entries_hash}), encoding="utf-8")


def _claude_code_hooks_drifted(
    installer: ClaudeCodeInstaller, binary: Path, entries: dict[str, dict[str, Any]]
) -> bool:
    """Whether settings.json is missing or diverges from any desired claude-code entry.

    Returns:
        True if any registered hook has no owned entry, or an owned entry that
        no longer matches what cline-hooks would install today.
    """
    config_path = installer.config_path(None)
    try:
        config: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    existing: dict[str, list[dict[str, Any]]] = config.get(installer.root_key, {})
    binary_names = installer.known_binary_names(ClaudeCodeProtocol, binary)
    for name, desired in entries.items():
        current = existing.get(name, [])
        owned = next(
            (entry for entry in current if isinstance(entry, dict) and installer.owns_entry(entry, binary_names)),
            None,
        )
        if owned is None or owned != desired:
            return True
    return False


def _repair_claude_code_install() -> None:
    """Re-run the claude-code installer if settings.json has drifted since the last check.

    Nothing on this machine re-runs `cline-hook install claude-code` on a bare
    upgrade, so SessionStart - the one hook that runs the full Python path -
    is the only reliable repair point. Guarded by a
    version-keyed stamp file so the settings.json read only happens again
    after cline-hooks' installed version actually changes.
    """
    binary = resolve_binary()
    entries = _claude_code_entries(binary)
    stamp = _InstallStamp(version=package_version(), entries_hash=_entries_hash(entries))

    if _read_install_stamp() == stamp:
        return

    installer = ClaudeCodeInstaller()
    if _claude_code_hooks_drifted(installer, binary, entries):
        logger.info("claude-code hook entries have drifted; repairing %s", installer.config_path(None))
        installer.install(ClaudeCodeProtocol, None)

    _write_install_stamp(stamp)


def _format_block_history(blocks: list[TaskBlockEvent]) -> str:
    """Format a list of block events into a readable bullet list.

    Args:
        blocks: Block events to format.

    Returns:
        Multi-line string with one bullet per event.
    """
    lines = ["This task was previously interrupted. Block history:"]
    lines.extend(f"- [{b.timestamp}] {b.tool_name} blocked: {b.reason}" for b in blocks)
    return "\n".join(lines)


@hook_handler(CanonicalHook.TASK_START)
def handle_task_start(hook: HookInputTaskStart) -> Outcome:
    """Handle TaskStart hook events.

    Args:
        hook: The hook input data.

    Returns:
        The merged Outcome for this task start.
    """
    if isinstance(get_protocol(), ClaudeCodeProtocol):
        try:
            _repair_claude_code_install()
        except Exception:
            logger.exception("Failed to check/repair the claude-code hook install")
        try:
            daemon_lifecycle.ensure()
        except Exception:
            logger.exception("Failed to ensure the loopback hook daemon is running")

    source = hook.taskStart.source if hook.taskStart else ""
    if source not in NO_RESET_TASK_START_SOURCES:
        _reset_skills(hook.taskId)
        _reset_memory(hook.taskId)
        _reset_agents(hook.taskId)
    parts: list[str] = []

    plugins = load_plugins()

    parts.extend(resolve_tooling_notes(plugins, hook.workspaceRoots))
    record_workspace(hook.taskId, hook.workspaceRoots)

    result = collect_hook_results(
        plugins,
        "TaskStart",
        task_id=hook.taskId,
        workspace_roots=hook.workspaceRoots,
        source=source,
        agent_type=hook.agentType,
    )
    parts.extend(result.notes)

    system_message: str | None = None
    if result.user_notes and get_protocol().supports_user_message():
        system_message = "\n\n".join(n.user_text for n in result.user_notes)

    return Outcome.allow("\n\n".join(parts), user_message=system_message or "")


@hook_handler(CanonicalHook.TASK_RESUME)
def handle_task_resume(hook: HookInputTaskResume) -> Outcome:
    """Handle TaskResume hook events.

    Args:
        hook: The hook input data.

    Returns:
        The merged Outcome for this task resume.
    """
    parts: list[str] = []

    blocks = _store.get_blocks(hook.taskId)
    if blocks:
        parts.append(_format_block_history(blocks))

    plugins = load_plugins()

    parts.extend(resolve_tooling_notes(plugins, hook.workspaceRoots))
    record_workspace(hook.taskId, hook.workspaceRoots)

    result = collect_hook_results(
        plugins,
        "TaskResume",
        task_id=hook.taskId,
        workspace_roots=hook.workspaceRoots,
        agent_type=hook.agentType,
        block_reasons=[block.reason for block in blocks],
    )
    parts.extend(result.notes)

    return Outcome.allow("\n\n".join(parts))


@hook_handler(CanonicalHook.TASK_CANCEL)
def handle_task_cancel(hook: HookInputTaskCancel) -> Outcome:
    """Handle TaskCancel hook events.

    Args:
        hook: The hook input data.

    Returns:
        The merged Outcome for this task cancel.
    """
    parts: list[str] = []

    blocks = _store.get_blocks(hook.taskId)
    if blocks:
        parts.append(_format_block_history(blocks))

    result = collect_hook_results(load_plugins(), "TaskCancel", task_id=hook.taskId)
    parts.extend(result.notes)

    return Outcome.allow("\n\n".join(parts))


@hook_handler(CanonicalHook.TASK_COMPLETE)
def handle_task_complete(hook: HookInputTaskComplete) -> Outcome:
    """Handle TaskComplete hook events.

    Args:
        hook: The hook input data.

    Returns:
        An empty ALLOW Outcome.
    """
    _store.clear_blocks(hook.taskId)
    _reset_memory(hook.taskId)
    _reset_agents(hook.taskId)
    reset_workspace(hook.taskId)
    collect_hook_results(load_plugins(), "TaskComplete", task_id=hook.taskId)
    return Outcome.allow()
