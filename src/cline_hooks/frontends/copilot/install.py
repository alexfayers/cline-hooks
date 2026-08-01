# ruff: noqa: T201
"""GitHub Copilot (VS Code) hook installation - patches ~/.copilot/hooks/cline-hooks.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cline_hooks.core.install import resolve_binary

_COPILOT_HOOKS: tuple[str, ...] = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PreCompact",
    "Stop",
)


def install_copilot() -> None:
    """Patch ~/.copilot/hooks/cline-hooks.json with cline-hooks entries.

    Merges hook entries into the existing hooks config, preserving entries
    from other sources. Skips events that already have a cline-hooks entry.
    """
    binary = resolve_binary()
    hooks_path = Path.home() / ".copilot" / "hooks" / "cline-hooks.json"

    if not hooks_path.exists():
        hooks_path.parent.mkdir(parents=True, exist_ok=True)
        config: dict[str, Any] = {}
    else:
        config = json.loads(hooks_path.read_text(encoding="utf-8"))

    existing_hooks: dict[str, list[dict[str, Any]]] = config.get("hooks", {})
    binary_str = str(binary)

    added = 0
    for event_name in _COPILOT_HOOKS:
        current = existing_hooks.get(event_name, [])
        existing_commands = {entry.get("command", "") for entry in current if isinstance(entry, dict)}

        if binary_str not in existing_commands:
            current.append({"type": "command", "command": binary_str})
            added += 1
        existing_hooks[event_name] = current

    config["hooks"] = existing_hooks
    hooks_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    if added:
        print(f"Patched {hooks_path} with {added} hook event(s).")
    else:
        print(f"{hooks_path} already has all cline-hooks entries.")
