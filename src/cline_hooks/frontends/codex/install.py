"""Codex hook installation - patches ~/.codex/hooks.json."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from cline_hooks.core.install import JsonHookInstaller


class CodexInstaller(JsonHookInstaller):
    """Installs cline-hooks into Codex's hooks file.

    Codex reuses Claude Code's config shape as well as its payload shape, so
    the default nested entry format applies unchanged.
    """

    help: ClassVar[str] = "Install Codex hooks into hooks.json"

    def config_path(self, target: str | None) -> Path:
        """Return Codex's hooks file.

        Returns:
            Path to ~/.codex/hooks.json.
        """
        return Path.home() / ".codex" / "hooks.json"
