"""Install/uninstall a per-user OS-supervised service that keeps the daemon running.

Picks the platform's native supervisor at runtime: a macOS LaunchAgent, or a
systemd user unit on Linux. An unsupported platform fails loudly rather than
silently doing nothing - the thin-client hook relay fails open when the
daemon is unreachable, so something has to keep the daemon up.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from cline_hooks.state.paths import get_data_dir

__all__ = [
    "UnsupportedPlatformError",
    "install",
    "platform",
    "status",
    "stop",
    "subprocess",
    "uninstall",
]

logger = logging.getLogger("hooks.daemon.service")

MANAGED_MARKER = "Managed by cline-hooks - see `cline-hook daemon service`."

_LAUNCHD_LABEL = "com.cline-hooks.daemon"
_SYSTEMD_UNIT_NAME = "cline-hooks-daemon.service"

_LAUNCHD_PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{_LAUNCHD_LABEL}.plist"
_SYSTEMD_UNIT_PATH = Path.home() / ".config" / "systemd" / "user" / _SYSTEMD_UNIT_NAME


class UnsupportedPlatformError(RuntimeError):
    """Raised when the current OS has no supported service supervisor."""


def _supervisor_binary(name: str) -> str:
    """Resolve a supervisor CLI's absolute path, falling back to the bare name if not found on PATH.

    Returns:
        The resolved absolute path, or `name` unchanged if not found on PATH.
    """
    return shutil.which(name) or name


def _launchd_plist_content(log_path: Path) -> str:
    """Build the LaunchAgent plist content.

    `KeepAlive=true` (the bare boolean, not the `SuccessfulExit` dict form)
    restarts the job on any exit, success or failure, until the job is
    unloaded - this is the load-bearing bit, since the daemon deliberately
    exits on a plugin-fingerprint change and must come back on the new code.
    launchd suspends a job that respawns in under ~10 seconds, so a daemon
    stuck in a fast crash loop would eventually stop being relaunched.

    Returns:
        The plist file's full XML content.
    """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<!-- {MANAGED_MARKER} -->
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>-m</string>
        <string>cline_hooks</string>
        <string>daemon</string>
        <string>serve</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
</dict>
</plist>
"""


def _systemd_unit_content(log_path: Path) -> str:
    """Build the systemd user unit content.

    `Restart=always` restarts on any exit, including one killed by a signal -
    except a deliberate `systemctl --user stop`, which systemd tracks as an
    intentional stop and does not restart. `WantedBy=default.target` is what
    makes `systemctl --user enable` start it at login.

    Returns:
        The unit file's full content.
    """
    return f"""# {MANAGED_MARKER}
[Unit]
Description=cline-hooks loopback daemon

[Service]
ExecStart={sys.executable} -m cline_hooks daemon serve
Restart=always
StandardOutput=append:{log_path}
StandardError=append:{log_path}

[Install]
WantedBy=default.target
"""


def _unit_path_and_content() -> tuple[Path, str]:
    """Return this platform's unit file path and content.

    Returns:
        The unit path and its full content.

    Raises:
        UnsupportedPlatformError: No supported service supervisor for this OS.
    """
    system = platform.system()
    log_path = get_data_dir() / "daemon.log"
    if system == "Darwin":
        return _LAUNCHD_PLIST_PATH, _launchd_plist_content(log_path)
    if system == "Linux":
        return _SYSTEMD_UNIT_PATH, _systemd_unit_content(log_path)
    msg = f"No supported service supervisor for platform {system!r} (supported: Darwin, Linux)."
    raise UnsupportedPlatformError(msg)


def _activate(path: Path) -> str:
    """Load/enable the just-written unit so it takes effect without a re-login.

    Returns:
        A note on whether activation succeeded.
    """
    system = platform.system()
    if system == "Darwin":
        launchctl = _supervisor_binary("launchctl")
        result = subprocess.run([launchctl, "load", str(path)], check=False, capture_output=True, text=True)
    else:
        systemctl = _supervisor_binary("systemctl")
        subprocess.run([systemctl, "--user", "daemon-reload"], check=False)
        result = subprocess.run(
            [systemctl, "--user", "enable", "--now", _SYSTEMD_UNIT_NAME],
            check=False,
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        return f"Activation command failed (exit {result.returncode}): {result.stderr.strip()}"
    return "Activated - the daemon will start at login and restart if it exits."


def _deactivate(path: Path) -> None:
    """Unload/disable the unit, best-effort."""
    system = platform.system()
    if system == "Darwin":
        subprocess.run([_supervisor_binary("launchctl"), "unload", str(path)], check=False)
    else:
        subprocess.run([_supervisor_binary("systemctl"), "--user", "disable", "--now", _SYSTEMD_UNIT_NAME], check=False)


def is_installed() -> bool:
    """Whether a cline-hooks-managed service unit is currently installed.

    Returns:
        True if this platform's unit file exists and carries our marker;
        False if absent, foreign, or the platform has no supported
        supervisor at all.
    """
    try:
        path, _ = _unit_path_and_content()
    except UnsupportedPlatformError:
        return False
    return path.exists() and _is_ours(path)


def _is_ours(path: Path) -> bool:
    """Whether `path` carries cline-hooks' managed marker.

    Returns:
        True if the file exists and carries the marker; False if absent, or
        present but foreign.
    """
    try:
        return MANAGED_MARKER in path.read_text(encoding="utf-8")
    except OSError:
        return False


def install() -> str:
    """Write and activate this platform's supervisor unit for the daemon.

    Idempotent - re-running it overwrites the same unit file in place rather
    than erroring or duplicating.

    Returns:
        A human-readable summary of what was written, where, and whether
        activation succeeded.

    Raises:
        UnsupportedPlatformError: No supported service supervisor for this OS.
    """
    path, content = _unit_path_and_content()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    activation = _activate(path)
    return f"Wrote {path}\n{activation}"


def uninstall() -> str:
    """Deactivate and remove this platform's supervisor unit, if it's ours.

    Returns:
        A human-readable summary of what happened.

    Raises:
        UnsupportedPlatformError: No supported service supervisor for this OS.
        RuntimeError: The unit file exists but wasn't written by cline-hooks.
    """
    path, _ = _unit_path_and_content()
    if not path.exists():
        return f"No service unit found at {path}; nothing to do."
    if not _is_ours(path):
        msg = f"{path} exists but was not written by cline-hooks; refusing to remove it."
        raise RuntimeError(msg)

    _deactivate(path)
    path.unlink()
    return f"Removed {path}."


def stop() -> str:
    """Stop the daemon through the platform's own service manager, so it stays stopped.

    Unlike `lifecycle.stop()`'s SIGTERM, this is a stop the supervisor treats
    as intentional: `systemctl --user stop` is systemd's own carve-out to
    `Restart=always`, and `launchctl bootout` removes the job from launchd's
    active tracking so `KeepAlive` no longer applies to it. Neither disables
    start-at-login - re-running `install` (or the next login) brings it back.

    Returns:
        A human-readable summary of what happened.

    Raises:
        UnsupportedPlatformError: No supported service supervisor for this OS.
    """
    path, _ = _unit_path_and_content()
    if not path.exists() or not _is_ours(path):
        return f"No cline-hooks service unit installed at {path}; nothing to stop."

    system = platform.system()
    if system == "Darwin":
        target = f"gui/{os.getuid()}/{_LAUNCHD_LABEL}"
        result = subprocess.run(
            [_supervisor_binary("launchctl"), "bootout", target], check=False, capture_output=True, text=True
        )
    else:
        result = subprocess.run(
            [_supervisor_binary("systemctl"), "--user", "stop", _SYSTEMD_UNIT_NAME],
            check=False,
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        return f"Stop command failed (exit {result.returncode}): {result.stderr.strip()}"
    return "Stopped the daemon via the service supervisor."


def status() -> str:
    """Report whether this platform's supervisor unit is installed.

    Returns:
        A human-readable status line.
    """
    try:
        path, _ = _unit_path_and_content()
    except UnsupportedPlatformError as exc:
        return str(exc)
    if not path.exists():
        return f"No service unit installed (expected at {path})."
    if not _is_ours(path):
        return f"{path} exists but was not written by cline-hooks."
    return f"Service unit installed at {path}."
