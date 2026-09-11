# ruff: noqa: T201
"""Shared install machinery: one Installer per frontend, driven by its hook table.

An installer never names the hooks it installs - it reads them from the
frontend's own `supported_hooks`, so a frontend that gains a hook gains it in
its installer for free. Most frontends are configured by a JSON file holding a
`hooks` object, so `JsonHookInstaller` carries that whole merge-and-report
flow; a frontend only says where its config lives and what one entry looks
like.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from cline_hooks.core.protocol import HookRegistration, Protocol


@dataclass(frozen=True)
class InstallArgument:
    """The single positional argument a frontend's install subcommand takes."""

    name: str
    help: str


class Installer(ABC):
    """Installs cline-hooks entry points for one frontend.

    Attributes:
        help: Help text for this frontend's `cline-hook install` subcommand.
        argument: The subcommand's positional argument, or None where it takes
            none.
    """

    help: ClassVar[str]
    argument: ClassVar[InstallArgument | None] = None

    @abstractmethod
    def install(self, protocol_cls: type[Protocol], target: str | None) -> None:
        """Install every hook `protocol_cls` registers.

        Args:
            protocol_cls: The frontend's Protocol class, whose
                `supported_hooks` names the hooks to install.
            target: The subcommand's positional argument, where it declares one.
        """


def resolve_binary() -> Path:
    """Resolve the path to the cline-hook binary.

    Returns:
        Path to the binary, preferring existing files.
    """
    scripts_dir = Path(sys.executable).parent
    candidates = (
        scripts_dir / "cline-hook",
        scripts_dir / "cline-hook.exe",
        scripts_dir / "cline-hook.cmd",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


class JsonHookInstaller(Installer):
    """Installer for frontends configured by a JSON file holding a `hooks` object.

    Merges an entry per registered hook into that object, preserving entries
    from other sources and skipping events that already point at this binary.

    Attributes:
        must_exist: Whether the config file must already exist, rather than
            being created on demand.
    """

    must_exist: ClassVar[bool] = False

    @abstractmethod
    def config_path(self, target: str | None) -> Path:
        """Return the JSON config file to patch.

        Args:
            target: The subcommand's positional argument, where it declares one.

        Returns:
            Path to the frontend's hook config file.
        """

    def build_entry(
        self, binary: Path, registration: HookRegistration
    ) -> dict[str, Any]:
        """Build one hook entry for the frontend's config.

        Defaults to the nested "hook group" shape, in which an entry carries an
        optional matcher and a list of commands.

        Args:
            binary: Path to the cline-hook binary.
            registration: The hook being installed.

        Returns:
            One entry for this hook event's list.
        """
        entry: dict[str, Any] = {
            "hooks": [{"type": "command", "command": str(binary)}],
        }
        if registration.matcher is not None:
            entry["matcher"] = registration.matcher
        return entry

    def entry_commands(self, entry: dict[str, Any]) -> set[str]:
        """Return the commands an existing config entry already runs.

        Args:
            entry: One entry from the config's hook event list.

        Returns:
            The commands the entry runs, used to skip re-adding this binary.
        """
        return {
            str(hook.get("command", ""))
            for hook in entry.get("hooks", [])
            if isinstance(hook, dict)
        }

    def _read_config(self, config_path: Path) -> dict[str, Any]:
        """Read the frontend's JSON config, creating its directory if allowed.

        Args:
            config_path: Path to the config file.

        Returns:
            The parsed config, or an empty config where the file may be created.
        """
        if config_path.exists():
            config: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
            return config
        if self.must_exist:
            print(f"error: {config_path} does not exist", file=sys.stderr)
            sys.exit(1)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        return {}

    def install(self, protocol_cls: type[Protocol], target: str | None) -> None:
        """Patch the frontend's JSON config with an entry per registered hook.

        Args:
            protocol_cls: The frontend's Protocol class.
            target: The subcommand's positional argument, where it declares one.
        """
        binary = resolve_binary()
        binary_str = str(binary)
        config_path = self.config_path(target)
        config = self._read_config(config_path)

        existing: dict[str, list[dict[str, Any]]] = config.get("hooks", {})
        added = 0
        for registration in protocol_cls.supported_hooks.values():
            current = existing.get(registration.native_name, [])
            installed = {
                command
                for entry in current
                if isinstance(entry, dict)
                for command in self.entry_commands(entry)
            }
            if binary_str not in installed:
                current.append(self.build_entry(binary, registration))
                added += 1
            existing[registration.native_name] = current

        config["hooks"] = existing
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        if added:
            print(f"Patched {config_path} with {added} hook event(s).")
        else:
            print(f"{config_path} already has all cline-hooks entries.")
