# ruff: file-ignore[print]
"""Shared install machinery: one Installer per frontend, driven by its hook table.

An installer never names the hooks it installs - it reads them from the
frontend's own `supported_hooks`.
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
        argument: The subcommand's positional argument, if it takes one.
    """

    help: ClassVar[str]
    argument: ClassVar[InstallArgument | None] = None

    @abstractmethod
    def install(self, protocol_cls: type[Protocol], target: str | None) -> None:
        """Install every hook `protocol_cls` registers.

        Args:
            protocol_cls: The frontend's Protocol class.
            target: The subcommand's positional argument, if it takes one.
        """


def resolve_binary(name: str = "cline-hook") -> Path:
    """Resolve the path to a console-script binary installed alongside this interpreter.

    Args:
        name: The script's base name, e.g. "cline-hook" or "cline-hook-guard".

    Returns:
        Path to the binary, preferring existing files.
    """
    scripts_dir = Path(sys.executable).parent
    candidates = (
        scripts_dir / name,
        scripts_dir / f"{name}.exe",
        scripts_dir / f"{name}.cmd",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


class JsonHookInstaller(Installer):
    """Installer for frontends configured by a JSON file of hook events.

    Merges an entry per registered hook into the object under `root_key`,
    preserving entries from other sources and skipping events already pointing
    at this binary.

    Attributes:
        must_exist: Whether the config file must already exist, rather than
            being created on demand.
        root_key: The config key holding the object of hook events.
        supports_thin_client: Whether this installer's frontend may point a
            registration's command at a different binary than the resolved
            `cline-hook` one, per that registration's own `binary_name`. A
            registration's `binary_name` can be inherited from a shared spec
            (Codex and Copilot reuse Claude Code's `supported_hooks`), so it
            alone isn't enough to decide - only frontends that actually
            support a thin-client binary should honour it.
    """

    must_exist: ClassVar[bool] = False
    root_key: ClassVar[str] = "hooks"
    supports_thin_client: ClassVar[bool] = False

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

    def entry_commands(self, entry: dict[str, Any]) -> set[str]:
        """Return the commands an existing config entry already runs.

        Args:
            entry: One entry from the config's hook event list.

        Returns:
            The entry's commands, used to skip re-adding this binary. A hook
            with no "command" key (e.g. an http-transport hook) contributes
            nothing, rather than a false empty-string entry.
        """
        return {str(hook["command"]) for hook in entry.get("hooks", []) if isinstance(hook, dict) and "command" in hook}

    def known_binary_names(self, protocol_cls: type[Protocol], binary: Path) -> frozenset[str]:
        """Return every binary basename this installer may legitimately have written.

        Args:
            protocol_cls: The frontend's Protocol class.
            binary: Path to the resolved default `cline-hook` binary.

        Returns:
            `binary`'s own basename, plus the resolved basename of every
            registration's `binary_name` this installer actually honours -
            e.g. `cline-hook-guard` alongside `cline-hook`, so an entry
            migrating between cline-hooks' own sibling binaries is still
            recognised as ours rather than duplicated.
        """
        names = {binary.name}
        if self.supports_thin_client:
            names.update(
                resolve_binary(registration.binary_name).name
                for registration in protocol_cls.supported_hooks.values()
                if registration.binary_name is not None
            )
        return frozenset(names)

    def owns_entry(self, entry: dict[str, Any], binary_names: frozenset[str]) -> bool:
        """Whether an existing config entry is one of cline-hooks' own binaries, in any form it emits.

        Args:
            entry: One entry from the config's hook event list.
            binary_names: Every basename cline-hooks may legitimately have
                written, from `known_binary_names()`.

        Returns:
            True if this entry was installed by cline-hooks and should be
            replaced/removed on reinstall rather than left alone.
        """
        return self._owns_command_entry(entry, binary_names)

    def _owns_command_entry(self, entry: dict[str, Any], binary_names: frozenset[str]) -> bool:
        """Whether an entry runs one of cline-hooks' own binaries, by exact basename.

        Args:
            entry: One entry from the config's hook event list.
            binary_names: Every basename cline-hooks may legitimately have
                written, from `known_binary_names()`.

        Returns:
            True if any command the entry runs exactly matches one of the
            known basenames.
        """
        return any(Path(cmd).name in binary_names for cmd in self.entry_commands(entry))

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

    def entry_binary(self, registration: HookRegistration, binary: Path) -> Path:
        """Return the binary this registration's entry should actually run.

        Returns:
            `resolve_binary(registration.binary_name)` where this installer
            supports thin-client binaries and the registration names one,
            otherwise the resolved default `binary`.
        """
        return (
            resolve_binary(registration.binary_name)
            if self.supports_thin_client and registration.binary_name is not None
            else binary
        )

    def _reconcile_registration(
        self,
        current: list[dict[str, Any]],
        registration: HookRegistration,
        binary: Path,
        binary_names: frozenset[str],
    ) -> str:
        """Reconcile one hook registration's entries in-place against the desired state.

        Returns:
            One of "added", "migrated", "unchanged".
        """
        entry_binary = self.entry_binary(registration, binary)
        owned_indices = [
            index
            for index, entry in enumerate(current)
            if isinstance(entry, dict) and self.owns_entry(entry, binary_names)
        ]
        desired = self.build_entry(entry_binary, registration)
        if not owned_indices:
            current.append(desired)
            return "added"

        first_index = owned_indices[0]
        status = "unchanged"
        if current[first_index] != desired:
            current[first_index] = desired
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

    def install(self, protocol_cls: type[Protocol], target: str | None) -> None:
        """Patch the frontend's JSON config with an entry per registered hook.

        Args:
            protocol_cls: The frontend's Protocol class.
            target: The subcommand's positional argument, if it takes one.
        """
        binary = resolve_binary()
        binary_names = self.known_binary_names(protocol_cls, binary)
        config_path = self.config_path(target)
        config = self._read_config(config_path)

        existing: dict[str, list[dict[str, Any]]] = config.get(self.root_key, {})
        counts = {"added": 0, "migrated": 0, "unchanged": 0}
        for registration in protocol_cls.supported_hooks.values():
            current = existing.get(registration.native_name, [])
            status = self._reconcile_registration(current, registration, binary, binary_names)
            counts[status] += 1
            existing[registration.native_name] = current

        config[self.root_key] = existing
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        self._report_install_result(config_path, counts)
