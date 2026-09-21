# ruff: file-ignore[print]
"""Pi hook installation - writes a bridge extension into pi's extensions directory."""

from __future__ import annotations

from importlib.resources import files
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from cline_hooks.core.install import Installer, resolve_binary
from cline_hooks.daemon.client import retire_daemon

if TYPE_CHECKING:
    from cline_hooks.core.protocol import Protocol

_BINARIES_PLACEHOLDER = '{ __CLINE_HOOK_EVENT__: "__CLINE_HOOK_BINARY__" }'


def agent_dir() -> Path:
    """Return pi's config directory.

    Returns:
        `$PI_CODING_AGENT_DIR` where set, else ~/.pi/agent.
    """
    override = os.environ.get("PI_CODING_AGENT_DIR")
    return Path(override).expanduser() if override else Path.home() / ".pi" / "agent"


class PiInstaller(Installer):
    """Installs cline-hooks as a pi extension.

    Pi runs no hook commands, only TypeScript extensions, so the installer
    writes one that pipes each registered event to the cline-hook binary.
    """

    help: ClassVar[str] = "Install Pi hooks as an extension in ~/.pi/agent/extensions/"

    def extension_path(self) -> Path:
        """Return where the bridge extension is written.

        Returns:
            Path to cline-hooks.ts in pi's global extensions directory.
        """
        return agent_dir() / "extensions" / "cline-hooks.ts"

    def install(self, protocol_cls: type[Protocol], target: str | None, *, force: bool = False) -> None:
        """Write the bridge extension, pointed at the resolved binaries.

        Args:
            protocol_cls: The pi protocol; the extension relays its hooks.
            target: Unused; pi's install takes no argument.
            force: Unused; the extension is always repointed at the resolved binaries.
        """
        template = files(__package__).joinpath("extension.ts").read_text(encoding="utf-8")
        dest = self.extension_path()
        binaries = {
            registration.native_name: str(resolve_binary(registration.binary_name))
            for registration in protocol_cls.supported_hooks.values()
        }
        content = template.replace(_BINARIES_PLACEHOLDER, json.dumps(binaries))
        if dest.exists() and dest.read_text(encoding="utf-8") == content:
            print(f"{dest} is already up to date.")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            print(f"Wrote {dest}.")
        if protocol_cls.uses_guard():
            retire_daemon()
