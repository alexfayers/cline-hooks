"""Claude Code hook installation - patches ~/.claude/settings.json."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from cline_hooks.core.install import JsonHookInstaller

if TYPE_CHECKING:
    from cline_hooks.core.protocol import Protocol


class ClaudeCodeInstaller(JsonHookInstaller):
    """Installs cline-hooks into Claude Code's user settings."""

    help: ClassVar[str] = "Install Claude Code hooks into settings"
    supports_thin_client: ClassVar[bool] = True

    def config_path(self, target: str | None) -> Path:
        """Return Claude Code's user settings file.

        Returns:
            Path to ~/.claude/settings.json.
        """
        return Path.home() / ".claude" / "settings.json"

    def install(self, protocol_cls: type[Protocol], target: str | None) -> None:
        """Patch settings.json, then best-effort retire any running daemon.

        A failed retire (no daemon running) is swallowed.

        Args:
            protocol_cls: The frontend's Protocol class.
            target: The subcommand's positional argument, if it takes one.
        """
        super().install(protocol_cls, target)
        from cline_hooks.core.daemon_config import load_or_create  # ruff: ignore[import-outside-top-level]
        from cline_hooks.daemon.client import post_retire  # ruff: ignore[import-outside-top-level]

        daemon_config = load_or_create()
        post_retire(daemon_config.port, daemon_config.token)
