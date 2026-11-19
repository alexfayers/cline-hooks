# ruff: file-ignore[print]
"""Opencode hook installation - not available until the bridge plugin ships."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import TYPE_CHECKING, ClassVar, NoReturn

from cline_hooks.core.install import Installer

if TYPE_CHECKING:
    from cline_hooks.core.protocol import Protocol


def config_dir() -> Path:
    """Return opencode's global config directory.

    Returns:
        Path to ~/.config/opencode.
    """
    return Path.home() / ".config" / "opencode"


class OpencodeInstaller(Installer):
    """Placeholder installer: opencode runs plugins, not hook commands, and the bridge plugin is not written yet."""

    help: ClassVar[str] = "Install opencode hooks (not available yet)"

    def install(self, protocol_cls: type[Protocol], target: str | None, *, force: bool = False) -> NoReturn:
        """Refuse to install, since there is no bridge plugin to write yet.

        Args:
            protocol_cls: Unused.
            target: Unused; opencode's install takes no argument.
            force: Unused.
        """
        print("error: opencode hooks cannot be installed yet.", file=sys.stderr)
        sys.exit(1)
