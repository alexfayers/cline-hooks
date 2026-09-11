"""Kiro hook installation - patches an agent config JSON."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from cline_hooks.core.install import InstallArgument, JsonHookInstaller

if TYPE_CHECKING:
    from cline_hooks.core.protocol import HookRegistration


class KiroInstaller(JsonHookInstaller):
    """Installs cline-hooks into a named Kiro agent config.

    Kiro's entries are flat - one command per entry, with the matcher
    alongside it - and the agent config must already exist, since cline-hooks
    has no way to author a valid agent from scratch.
    """

    help: ClassVar[str] = "Install Kiro hooks into agent config"
    argument: ClassVar[InstallArgument | None] = InstallArgument(
        name="agent_config", help="Path to Kiro agent config JSON file"
    )
    must_exist: ClassVar[bool] = True

    def config_path(self, target: str | None) -> Path:
        """Return the agent config named on the command line.

        Returns:
            Path to the agent JSON file to patch.
        """
        return Path(target or "")

    def build_entry(
        self, binary: Path, registration: HookRegistration
    ) -> dict[str, Any]:
        """Build one flat Kiro hook entry.

        Returns:
            A command entry, described so it is recognisable in the agent config.
        """
        entry: dict[str, Any] = {
            "command": str(binary),
            "description": f"cline-hooks {registration.native_name}",
        }
        if registration.matcher is not None:
            entry["matcher"] = registration.matcher
        return entry

    def entry_commands(self, entry: dict[str, Any]) -> set[str]:
        """Return the command a flat Kiro entry runs.

        Returns:
            The entry's own command.
        """
        return {str(entry.get("command", ""))}
