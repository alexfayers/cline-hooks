"""Antigravity hook installation - patches ~/.gemini/config/hooks.json."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from cline_hooks.core.install import JsonHookInstaller

if TYPE_CHECKING:
    from cline_hooks.core.protocol import HookRegistration


class AntigravityInstaller(JsonHookInstaller):
    """Installs cline-hooks into Antigravity's user hooks file.

    Antigravity's hooks.json maps a hook's name to its event configuration, so
    everything cline-hooks installs lives under its own name. A tool event's
    entries are hook groups behind a matcher; every other event's are handlers
    listed directly under the event key.
    """

    help: ClassVar[str] = "Install Antigravity hooks into ~/.gemini/config/hooks.json"
    root_key: ClassVar[str] = "cline-hooks"

    def config_path(self, target: str | None) -> Path:
        """Return Antigravity's user hooks file.

        Returns:
            Path to ~/.gemini/config/hooks.json.
        """
        return Path.home() / ".gemini" / "config" / "hooks.json"

    def build_entry(self, binary: Path, registration: HookRegistration, *, http: bool = False) -> dict[str, Any]:
        """Build one Antigravity hook entry in the event's own structure.

        Antigravity has no http-transport registrations, so `http` is unused.

        Returns:
            A hook group carrying the matcher where the event matches on tool
            name, otherwise a bare handler.
        """
        handler = {"type": "command", "command": str(binary)}
        if registration.matcher is None:
            return handler
        return {"matcher": registration.matcher, "hooks": [handler]}

    def entry_commands(self, entry: dict[str, Any]) -> set[str]:
        """Return the commands an entry of either structure already runs.

        Returns:
            The commands in the entry's hook group, or the entry's own command.
        """
        if "hooks" in entry:
            return super().entry_commands(entry)
        return {str(entry.get("command", ""))}
