# ruff: file-ignore[print]
"""Shared install machinery: one Installer per frontend, driven by its hook table.

An installer never names the hooks it installs - it reads them from the
frontend's own `supported_hooks`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from importlib.metadata import distribution
from importlib.resources import files
import json
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING, Any, ClassVar

from cline_hooks.core.frontend import FRONTEND_ENV_KEY
from cline_hooks.core.user_install import is_venv_scripts_dir, resolve_user_binary

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
    def install(self, protocol_cls: type[Protocol], target: str | None, *, force: bool = False) -> None:
        """Install every hook `protocol_cls` registers.

        Args:
            protocol_cls: The frontend's Protocol class.
            target: The subcommand's positional argument, if it takes one.
            force: Whether to repoint existing entries even where their binary exists.
        """

    @abstractmethod
    def uninstall(self, protocol_cls: type[Protocol], target: str | None) -> None:
        """Remove only what `install` wrote, leaving other tools' entries.

        Args:
            protocol_cls: The frontend's Protocol class.
            target: The subcommand's positional argument, if it takes one.
        """


def binary_names() -> tuple[str, ...]:
    """Return the platform variants of this distribution's console script name.

    Returns:
        The bare, `.exe` and `.cmd` file names.
    """
    base = next(
        entry_point.name
        for entry_point in distribution("cline-hooks").entry_points
        if entry_point.group == "console_scripts"
    )
    return (base, f"{base}.exe", f"{base}.cmd")


def resolve_binary() -> Path:
    """Resolve the path to the user-wide cline-hook binary.

    Returns:
        Path to the binary found outside any virtual environment.
    """
    name = binary_names()[0]
    binary = resolve_user_binary(name)
    if binary is None:
        print(f"error: no user-wide {name} found on PATH. Install cline-hooks as a tool first.", file=sys.stderr)
        sys.exit(1)
    return binary


_BINARY_PLACEHOLDER = '"__CLINE_HOOK_BINARY__"'


def write_bridge(package: str, template: str, dest: Path) -> None:
    """Write a bridge script from a template in `package`, pointed at the resolved binary.

    Frontends without command hooks run a script of their own that relays each
    event to cline-hook; the template names the binary `__CLINE_HOOK_BINARY__`.

    Args:
        package: The frontend package holding the template.
        template: The template's file name.
        dest: Where the bridge is written.
    """
    source = files(package).joinpath(template).read_text(encoding="utf-8")
    content = source.replace(_BINARY_PLACEHOLDER, json.dumps(str(resolve_binary())))
    if dest.exists() and dest.read_text(encoding="utf-8") == content:
        print(f"{dest} is already up to date.")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    print(f"Wrote {dest}.")


def remove_bridge(dest: Path) -> None:
    """Delete a bridge script written by `write_bridge`.

    Args:
        dest: Where the bridge was written.
    """
    if not dest.exists():
        print(f"{dest} does not exist.")
        return
    dest.unlink()
    print(f"Removed {dest}.")


class JsonHookInstaller(Installer):
    """Installer for frontends configured by a JSON file of hook events.

    Merges an entry per registered hook into the object under `root_key`,
    preserving entries from other sources and pointing existing cline-hook entries
    whose binary is missing or inside a virtual environment, or all of them when forced,
    at the resolved binary.

    Attributes:
        must_exist: Whether the config file must already exist, rather than
            being created on demand.
        root_key: The config key holding the object of hook events.
        runs_in_shell: Whether the frontend runs hook commands through a shell.
    """

    must_exist: ClassVar[bool] = False
    root_key: ClassVar[str] = "hooks"
    runs_in_shell: ClassVar[bool] = True

    def command(self, binary: str, protocol_cls: type[Protocol]) -> str:
        """Build the command a hook entry runs.

        Returns:
            The binary, prefixed with the frontend variable where a shell runs it.
        """
        spec = protocol_cls.frontend_spec
        if spec is None or not self.runs_in_shell or os.name == "nt":
            return binary
        return f"{FRONTEND_ENV_KEY}={spec.name} {binary}"

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

    def install(self, protocol_cls: type[Protocol], target: str | None, *, force: bool = False) -> None:
        """Patch the frontend's JSON config with an entry per registered hook.

        Args:
            protocol_cls: The frontend's Protocol class.
            target: The subcommand's positional argument, if it takes one.
            force: Whether to repoint existing entries even where their binary exists outside a virtual environment.
        """
        binary = resolve_binary()
        names = binary_names()
        config_path = self.config_path(target)
        config = self._read_config(config_path)

        existing: dict[str, list[dict[str, Any]]] = config.get(self.root_key, {})
        added = 0
        rewritten = 0
        for registration in protocol_cls.supported_hooks.values():
            current = existing.get(registration.native_name, [])
            installed = False
            for entry in current:
                if not isinstance(entry, dict):
                    continue
                for handler in self.entry_handlers(entry):
                    old = str(handler.get("command", "")).removeprefix(self.command("", protocol_cls))
                    if Path(old).name not in names:
                        continue
                    installed = True
                    keep = not force and Path(old).exists() and not is_venv_scripts_dir(Path(old).parent)
                    command = self.command(old if keep else str(binary), protocol_cls)
                    if handler["command"] != command:
                        handler["command"] = command
                        rewritten += 1
            if not installed:
                new_entry = self.build_entry(binary, registration)
                for handler in self.entry_handlers(new_entry):
                    handler["command"] = self.command(str(binary), protocol_cls)
                current.append(new_entry)
                added += 1
            existing[registration.native_name] = current

        config[self.root_key] = existing
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        if added:
            print(f"Patched {config_path} with {added} hook event(s).")
        if rewritten:
            print(f"Updated the cline-hook path in {rewritten} hook(s) in {config_path}.")
        if not added and not rewritten:
            print(f"{config_path} already has all cline-hooks entries.")

    def uninstall(self, protocol_cls: type[Protocol], target: str | None) -> None:
        """Remove the cline-hook handlers from the frontend's JSON config.

        Drops an entry left with no handler, an event left with no entry, and
        the root key once empty. A missing or malformed file is left untouched.

        Args:
            protocol_cls: The frontend's Protocol class.
            target: The subcommand's positional argument, if it takes one.
        """
        names = binary_names()
        prefix = self.command("", protocol_cls)
        config_path = self.config_path(target)
        if not config_path.exists():
            print(f"{config_path} does not exist.")
            return
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except ValueError:
            config = None
        events = config.get(self.root_key, {}) if isinstance(config, dict) else None
        if not isinstance(events, dict):
            print(f"warning: {config_path} is not a valid hooks config, skipped.", file=sys.stderr)
            return

        def is_own(handler: dict[str, Any]) -> bool:
            return Path(str(handler.get("command", "")).removeprefix(prefix)).name in names

        removed = 0
        kept_events: dict[str, Any] = {}
        for event, entries in events.items():
            if not isinstance(entries, list):
                kept_events[event] = entries
                continue
            kept_entries = []
            for entry in entries:
                handlers = self.entry_handlers(entry) if isinstance(entry, dict) else []
                own = [handler for handler in handlers if is_own(handler)]
                removed += len(own)
                if handlers and len(own) == len(handlers):
                    continue
                if own:
                    entry["hooks"] = [handler for handler in entry["hooks"] if handler not in own]
                kept_entries.append(entry)
            if kept_entries or not entries:
                kept_events[event] = kept_entries
        if not removed:
            print(f"{config_path} has no cline-hooks entries.")
            return
        if kept_events:
            config[self.root_key] = kept_events
        else:
            del config[self.root_key]
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        print(f"Removed {removed} cline-hooks entries from {config_path}.")
