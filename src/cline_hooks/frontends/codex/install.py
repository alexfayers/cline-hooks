# ruff: noqa: T201
"""Codex hook installation - patches ~/.codex/hooks.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cline_hooks.core.install import build_hook_registrations, resolve_binary
from cline_hooks.frontends.codex.protocol import CodexProtocol


def _build_codex_hooks(binary: Path) -> dict[str, list[dict[str, object]]]:
    """Build the hooks section for ~/.codex/hooks.json.

    Codex reuses Claude Code's hook JSON shape exactly, so entries mirror
    CodexProtocol.supported_hooks (which aliases ClaudeCodeProtocol's).

    Args:
        binary: Path to the cline-hook binary.

    Returns:
        A dict suitable for the "hooks" key in ~/.codex/hooks.json.
    """
    hooks: dict[str, list[dict[str, object]]] = {}
    for registration in build_hook_registrations(CodexProtocol):
        entry: dict[str, object] = {
            "hooks": [{"type": "command", "command": str(binary)}],
        }
        if registration.matcher is not None:
            entry["matcher"] = registration.matcher
        hooks[registration.native_name] = [entry]
    return hooks


def install_codex() -> None:
    """Patch ~/.codex/hooks.json with cline-hooks entries.

    Merges hook entries into the existing hooks config, preserving entries
    from other sources. Skips events that already have a cline-hooks entry.
    """
    binary = resolve_binary()
    hooks_path = Path.home() / ".codex" / "hooks.json"

    if not hooks_path.exists():
        hooks_path.parent.mkdir(parents=True, exist_ok=True)
        config: dict[str, Any] = {}
    else:
        config = json.loads(hooks_path.read_text(encoding="utf-8"))

    existing_hooks: dict[str, list[dict[str, Any]]] = config.get("hooks", {})
    new_hooks = _build_codex_hooks(binary)
    binary_str = str(binary)

    added = 0
    for event_name, groups in new_hooks.items():
        current = existing_hooks.get(event_name, [])
        existing_commands: set[str] = set()
        for group in current:
            for hook in group.get("hooks", []):
                if isinstance(hook, dict):
                    existing_commands.add(str(hook.get("command", "")))

        if binary_str not in existing_commands:
            current.extend(groups)
            added += 1
        existing_hooks[event_name] = current

    config["hooks"] = existing_hooks
    hooks_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    if added:
        print(f"Patched {hooks_path} with {added} hook event(s).")
    else:
        print(f"{hooks_path} already has all cline-hooks entries.")
