"""Opencode hook installation - writes a bridge plugin into opencode's plugins directory."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from cline_hooks.core.install import Installer, remove_bridge, write_bridge

if TYPE_CHECKING:
    from cline_hooks.core.protocol import Protocol


def config_dir() -> Path:
    """Return opencode's global config directory, as opencode resolves it.

    Returns:
        `$OPENCODE_CONFIG_DIR`, else `$XDG_CONFIG_HOME/opencode`, else
        `~/.config/opencode`.
    """
    if override := os.environ.get("OPENCODE_CONFIG_DIR"):
        return Path(override).expanduser()
    if xdg := os.environ.get("XDG_CONFIG_HOME"):
        return Path(xdg).expanduser() / "opencode"
    return Path.home() / ".config" / "opencode"


class OpencodeInstaller(Installer):
    """Installs cline-hooks as an opencode 2.x plugin.

    Opencode runs no hook commands, only plugins, so the installer writes one
    that pipes each plugin hook to the cline-hook binary.
    """

    help: ClassVar[str] = "Install opencode hooks as a plugin in opencode's plugins/ directory"

    def plugin_path(self) -> Path:
        """Return where the bridge plugin is written.

        Returns:
            Path to cline-hooks.ts in opencode's global plugins directory.
        """
        return config_dir() / "plugins" / "cline-hooks.ts"

    def install(self, protocol_cls: type[Protocol], target: str | None, *, force: bool = False) -> None:
        """Write the bridge plugin, pointed at the resolved binary.

        Args:
            protocol_cls: The opencode protocol; the plugin relays its hooks.
            target: Unused; opencode's install takes no argument.
            force: Unused; the plugin is always repointed at the resolved binary.
        """
        write_bridge(__package__, "plugin.ts", self.plugin_path())

    def uninstall(self, protocol_cls: type[Protocol], target: str | None) -> None:
        """Delete the bridge plugin.

        Args:
            protocol_cls: Unused; the plugin is one file.
            target: Unused; opencode's install takes no argument.
        """
        remove_bridge(self.plugin_path())
