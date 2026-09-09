"""Antigravity hook installation - patches ~/.gemini/config/hooks.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cline_hooks.core.install import resolve_binary


def _build_antigravity_hooks(binary: Path) -> dict[str, Any]:
    """Build the cline-hooks event configurations for Antigravity hooks.json.

    Args:
        binary: Path to the cline-hook binary.

    Returns:
        A dict of event names to handler configurations matching Antigravity spec.
    """
    binary_str = str(binary)
    return {
        "PreToolUse": [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{binary_str} antigravity --event PreToolUse",
                        "timeout": 30,
                    }
                ],
            }
        ],
        "PostToolUse": [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{binary_str} antigravity --event PostToolUse",
                        "timeout": 30,
                    }
                ],
            }
        ],
        "Stop": [
            {
                "type": "command",
                "command": f"{binary_str} antigravity --event Stop",
                "timeout": 30,
            }
        ],
    }


def install_antigravity(config_dir: Path | None = None) -> Path:
    """Patch ~/.gemini/config/hooks.json with cline-hooks entries.

    Args:
        config_dir: Optional override for the config directory. Defaults to ~/.gemini/config.

    Returns:
        The path to the patched hooks.json file.
    """
    binary = resolve_binary()
    target_dir = config_dir or (Path.home() / ".gemini" / "config")
    hooks_path = target_dir / "hooks.json"

    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    if not hooks_path.exists() or hooks_path.stat().st_size == 0:
        config: dict[str, Any] = {}
    else:
        try:
            config = json.loads(hooks_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            config = {}

    config["cline-hooks"] = _build_antigravity_hooks(binary)
    hooks_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"Patched {hooks_path} with cline-hooks configuration.")
    return hooks_path
