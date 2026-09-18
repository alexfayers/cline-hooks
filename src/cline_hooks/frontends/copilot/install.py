"""GitHub Copilot hook installation - patches ~/.copilot/hooks/cline-hooks.json."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from cline_hooks.core.install import JsonHookInstaller

if TYPE_CHECKING:
    from cline_hooks.core.protocol import HookRegistration


class CopilotInstaller(JsonHookInstaller):
    """Installs cline-hooks into Copilot's hooks directory.

    Entries are flat command objects with no matcher, and cline-hooks gets its
    own file rather than patching a shared one.
    """

    help: ClassVar[str] = "Install GitHub Copilot hooks into ~/.copilot/hooks/"

    def config_path(self, target: str | None) -> Path:
        """Return cline-hooks' own file in Copilot's hooks directory.

        Returns:
            Path to ~/.copilot/hooks/cline-hooks.json.
        """
        return Path.home() / ".copilot" / "hooks" / "cline-hooks.json"

    def build_entry(self, binary: Path, registration: HookRegistration) -> dict[str, Any]:
        """Build one flat Copilot hook entry.

        Returns:
            A command entry; Copilot's format carries no matcher.
        """
        return {"type": "command", "command": str(binary)}

    def entry_commands(self, entry: dict[str, Any]) -> set[str]:
        """Return the command a flat Copilot entry runs.

        Returns:
            The entry's own command.
        """
        return {str(entry.get("command", ""))}
