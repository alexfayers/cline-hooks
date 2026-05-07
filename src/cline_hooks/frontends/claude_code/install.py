# ruff: noqa: T201
"""Claude Code hook installation - patches ~/.claude/settings.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cline_hooks.core.install import resolve_binary

_CLAUDE_CODE_HOOKS: dict[str, str | None] = {
    "SessionStart": None,
    "UserPromptSubmit": None,
    "PreToolUse": "",
    "PostToolUse": "",
    "Stop": None,
}


def _build_claude_code_hooks(binary: Path) -> dict[str, list[dict[str, object]]]:
    """Build the hooks section for Claude Code settings.json.

    Args:
        binary: Path to the cline-hook binary.

    Returns:
        A dict suitable for the "hooks" key in Claude Code settings.json.
    """
    hooks: dict[str, list[dict[str, object]]] = {}
    for event_name, matcher in _CLAUDE_CODE_HOOKS.items():
        entry: dict[str, object] = {
            "hooks": [{"type": "command", "command": str(binary)}],
        }
        if matcher is not None:
            entry["matcher"] = matcher
        hooks[event_name] = [entry]
    return hooks


def install_claude_code() -> None:
    """Patch ~/.claude/settings.json with cline-hooks entries.

    Merges hook entries into the existing hooks config, preserving entries
    from other sources. Skips events that already have a cline-hooks entry.
    """
    binary = resolve_binary()
    settings_path = Path.home() / ".claude" / "settings.json"

    if not settings_path.exists():
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings: dict[str, Any] = {}
    else:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))

    existing_hooks: dict[str, list[dict[str, Any]]] = settings.get("hooks", {})
    new_hooks = _build_claude_code_hooks(binary)
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

    settings["hooks"] = existing_hooks
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    if added:
        print(f"Patched {settings_path} with {added} hook event(s).")
    else:
        print(f"{settings_path} already has all cline-hooks entries.")
