# ruff: file-ignore[print]
"""Shared install machinery: one Installer per frontend, driven by its hook table.

An installer never names the hooks it installs - it reads them from the
frontend's own `supported_hooks`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, distribution, version
import json
from pathlib import Path
import shutil
import sys
from typing import TYPE_CHECKING, Any, ClassVar

from cline_hooks.daemon.client import retire_daemon

if TYPE_CHECKING:
    from cline_hooks.core.protocol import HookRegistration, Protocol

_DISTRIBUTION_NAME = "cline-hooks"


@dataclass(frozen=True)
class InstallArgument:
    """The single positional argument a frontend's install subcommand takes."""

    name: str
    help: str


class Installer(ABC):
    """Installs cline-hooks entry points for one frontend.

    Attributes:
        help: Help text for this frontend's `cline-hook install` subcommand.
        argument: The subcommand's positional argument, if it takes one.
    """

    help: ClassVar[str]
    argument: ClassVar[InstallArgument | None] = None

    @abstractmethod
    def install(self, protocol_cls: type[Protocol], target: str | None, *, force: bool = False) -> None:
        """Install every hook `protocol_cls` registers.

        Args:
            protocol_cls: The frontend's Protocol class.
            target: The subcommand's positional argument, if it takes one.
            force: Whether to repoint existing entries even where their binary exists.
        """


def package_version() -> str:
    """Return the installed cline-hooks distribution version.

    Returns:
        The version string, or "0" if the package isn't installed as a
        distribution.
    """
    try:
        return version(_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return "0"


def binary_names(script: str | None = None) -> tuple[str, ...]:
    """Return the platform variants of a console script name.

    Args:
        script: The script's base name, defaulting to this distribution's first console script.

    Returns:
        The bare, `.exe` and `.cmd` file names.
    """
    base = script or next(
        entry_point.name
        for entry_point in distribution(_DISTRIBUTION_NAME).entry_points
        if entry_point.group == "console_scripts"
    )
    return (base, f"{base}.exe", f"{base}.cmd")


def resolve_binary(name: str | None = None) -> Path:
    """Resolve the path to a console-script binary installed alongside this interpreter.

    Args:
        name: The script's base name, e.g. "cline-hook-guard"; defaults to the main cline-hook script.

    Returns:
        Path to the binary, preferring the PATH link to the running binary, then
        existing files.
    """
    scripts_dir = Path(sys.executable).parent
    variants = binary_names(name)
    candidates = tuple(scripts_dir / variant for variant in variants)
    own = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
    linked = shutil.which(variants[0])
    if linked and Path(linked).resolve() == own.resolve():
        return Path(linked)
    return own


class JsonHookInstaller(Installer):
    """Installer for frontends configured by a JSON file of hook events.

    Merges an entry per registered hook into the object under `root_key`,
    preserving entries from other sources and repointing cline-hook entries that run
    from this install, whose binary is missing, or all of them when forced.

    Attributes:
        must_exist: Whether the config file must already exist, rather than
            being created on demand.
        root_key: The config key holding the object of hook events.
    """

    must_exist: ClassVar[bool] = False
    root_key: ClassVar[str] = "hooks"

    @abstractmethod
    def config_path(self, target: str | None) -> Path:
        """Return the JSON config file to patch.

        Args:
            target: The subcommand's positional argument, if it takes one.

        Returns:
            Path to the frontend's hook config file.
        """

    def build_entry(self, binary: Path, registration: HookRegistration) -> dict[str, Any]:
        """Build one hook entry, in the nested "hook group" shape by default.

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

    def entry_handlers(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the command handlers of an existing config entry.

        Args:
            entry: One entry from the config's hook event list.

        Returns:
            The entry's handler objects, used to find and repoint a cline-hook binary.
        """
        return [hook for hook in entry.get("hooks", []) if isinstance(hook, dict)]

    def entry_commands(self, entry: dict[str, Any]) -> set[str]:
        """Return the commands an existing config entry already runs, skipping handlers with no "command"."""
        return {str(handler["command"]) for handler in self.entry_handlers(entry) if "command" in handler}

    def known_binary_names(self, protocol_cls: type[Protocol], binary: Path) -> frozenset[str]:
        """Return every binary basename this installer may legitimately have written."""
        return frozenset(
            {binary.name}
            | {
                resolve_binary(registration.binary_name).name
                for registration in protocol_cls.supported_hooks.values()
                if registration.binary_name
            }
        )

    def owns_entry(self, entry: dict[str, Any], binary_names: frozenset[str]) -> bool:
        """Return True if an existing config entry runs one of cline-hooks' own binaries, by exact basename."""
        return any(Path(cmd).name in binary_names for cmd in self.entry_commands(entry))

    def _runs_from(self, entry: dict[str, Any], scripts_dir: Path) -> bool:
        """Return True if an existing config entry runs a command located in `scripts_dir`."""
        return any(Path(cmd).parent == scripts_dir for cmd in self.entry_commands(entry))

    def _read_config(self, config_path: Path) -> dict[str, Any]:
        """Read the frontend's JSON config, creating its directory if allowed.

        Args:
            config_path: Path to the config file.

        Returns:
            The parsed config, or an empty one where the file may be created.
        """
        if config_path.exists():
            config: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
            return config
        if self.must_exist:
            print(f"error: {config_path} does not exist", file=sys.stderr)
            sys.exit(1)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        return {}

    def _should_repoint(
        self, entry: dict[str, Any], binary: Path, binary_names: frozenset[str], *, force: bool
    ) -> bool:
        """Whether an owned entry may be pointed at this install's binaries.

        Args:
            entry: An owned entry from the config's hook event list.
            binary: Path to the resolved default `cline-hook` binary.
            binary_names: Basenames from `known_binary_names()`.
            force: Whether to repoint even where the entry's binary exists elsewhere.

        Returns:
            True when forced, when the entry runs from this install, or when
            one of its cline-hook commands no longer exists.
        """
        if force or self._runs_from(entry, binary.parent) or self._runs_from(entry, Path(sys.executable).parent):
            return True
        return any(
            not Path(command).exists() for command in self.entry_commands(entry) if Path(command).name in binary_names
        )

    def _reconcile_registration(
        self,
        current: list[dict[str, Any]],
        registration: HookRegistration,
        binary: Path,
        binary_names: frozenset[str],
        *,
        force: bool,
    ) -> str:
        """Reconcile one hook registration's entries in-place against the desired state.

        Repoints the first owned entry's cline-hook commands, keeping its other
        fields, and drops any further owned entries.

        Returns:
            One of "added", "migrated", "unchanged".
        """
        entry_binary = resolve_binary(registration.binary_name)
        owned_indices = [
            index
            for index, entry in enumerate(current)
            if isinstance(entry, dict) and self.owns_entry(entry, binary_names)
        ]
        if not owned_indices:
            current.append(self.build_entry(entry_binary, registration))
            return "added"

        first = current[owned_indices[0]]
        if not self._should_repoint(first, binary, binary_names, force=force):
            return "unchanged"
        status = "unchanged"
        for handler in self.entry_handlers(first):
            if Path(str(handler.get("command", ""))).name in binary_names and handler["command"] != str(entry_binary):
                handler["command"] = str(entry_binary)
                status = "migrated"
        for index in reversed(owned_indices[1:]):
            del current[index]
        return status

    def _report_install_result(self, config_path: Path, counts: dict[str, int]) -> None:
        if not counts["added"] and not counts["migrated"]:
            print(f"{config_path} already has all cline-hooks entries.")
            return
        parts = [f"{counts[status]} {status}" for status in ("added", "migrated", "unchanged") if counts[status]]
        print(f"Patched {config_path}: {', '.join(parts)}.")

    def install(self, protocol_cls: type[Protocol], target: str | None, *, force: bool = False) -> None:
        """Patch the frontend's JSON config with an entry per registered hook.

        Args:
            protocol_cls: The frontend's Protocol class.
            target: The subcommand's positional argument, if it takes one.
            force: Whether to repoint existing entries even where their binary exists.
        """
        binary = resolve_binary()
        binary_names = self.known_binary_names(protocol_cls, binary)
        config_path = self.config_path(target)
        config = self._read_config(config_path)

        existing: dict[str, list[dict[str, Any]]] = config.get(self.root_key, {})
        counts = {"added": 0, "migrated": 0, "unchanged": 0}
        for registration in protocol_cls.supported_hooks.values():
            current = existing.get(registration.native_name, [])
            status = self._reconcile_registration(current, registration, binary, binary_names, force=force)
            counts[status] += 1
            existing[registration.native_name] = current

        config[self.root_key] = existing
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        self._report_install_result(config_path, counts)
        if protocol_cls.uses_guard():
            retire_daemon()
