# ruff: noqa: T201
"""Kiro hook installation - patches agent config JSON."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from cline_hooks.core.install import resolve_binary

_KIRO_HOOKS: dict[str, str | None] = {
    "agentSpawn": None,
    "userPromptSubmit": None,
    "preToolUse": "*",
    "postToolUse": "*",
    "stop": None,
}


def _build_kiro_hooks(binary: Path) -> dict[str, list[dict[str, str]]]:
    """Build the hooks section for a Kiro agent config.

    Args:
        binary: Path to the cline-hook binary.

    Returns:
        A dict suitable for the "hooks" key in a Kiro agent JSON.
    """
    hooks: dict[str, list[dict[str, str]]] = {}
    for hook_name, matcher in _KIRO_HOOKS.items():
        entry: dict[str, str] = {
            "command": str(binary),
            "description": f"cline-hooks {hook_name}",
        }
        if matcher is not None:
            entry["matcher"] = matcher
        hooks[hook_name] = [entry]
    return hooks


def install_kiro(agent_config_path: str) -> None:
    """Patch a Kiro agent config JSON file with cline-hooks entries.

    Args:
        agent_config_path: Path to the agent JSON file to patch.
    """
    binary = resolve_binary()
    config_path = Path(agent_config_path)

    if not config_path.exists():
        print(f"error: {config_path} does not exist", file=sys.stderr)
        sys.exit(1)

    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["hooks"] = _build_kiro_hooks(binary)
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(f"Patched {config_path} with {len(_KIRO_HOOKS)} hooks.")
