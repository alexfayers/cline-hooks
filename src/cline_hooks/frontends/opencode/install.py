# ruff: file-ignore[print]
"""Opencode hook installation - writes a bridge plugin into opencode's plugins directory."""

from __future__ import annotations

from importlib.resources import files
import json
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from cline_hooks.core.install import Installer, resolve_binary

if TYPE_CHECKING:
    from cline_hooks.core.protocol import Protocol

_BINARY_PLACEHOLDER = '"__CLINE_HOOK_BINARY__"'


def config_dir() -> Path:
    """Return opencode's global config directory.

    Returns:
        Path to ~/.config/opencode.
    """
    return Path.home() / ".config" / "opencode"


class OpencodeInstaller(Installer):
    """Installs cline-hooks as an opencode plugin.

    Opencode runs no hook commands, only JavaScript plugins, so the installer
    writes one that pipes each relayed event to the cline-hook binary.
    """

    help: ClassVar[str] = "Install opencode hooks as a plugin in ~/.config/opencode/plugins/"

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
        template = files(__package__).joinpath("plugin.ts").read_text(encoding="utf-8")
        dest = self.plugin_path()
        content = template.replace(_BINARY_PLACEHOLDER, json.dumps(str(resolve_binary())))
        if dest.exists() and dest.read_text(encoding="utf-8") == content:
            print(f"{dest} is already up to date.")
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        print(f"Wrote {dest}.")
