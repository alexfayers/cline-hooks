"""Claude Code hook installation - patches ~/.claude/settings.json."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from cline_hooks.core.install import JsonHookInstaller


class ClaudeCodeInstaller(JsonHookInstaller):
    """Installs cline-hooks into Claude Code's user settings."""

    help: ClassVar[str] = "Install Claude Code hooks into settings"

    def config_path(self, target: str | None) -> Path:
        """Return Claude Code's user settings file.

        Returns:
            Path to ~/.claude/settings.json.
        """
        return Path.home() / ".claude" / "settings.json"
