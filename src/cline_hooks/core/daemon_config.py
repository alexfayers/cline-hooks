"""The daemon's loopback port and bearer token, persisted alongside the user config."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import secrets
import tempfile
from typing import Any

from cline_hooks.config import config_dir

logger = logging.getLogger("hooks.daemon_config")

DEFAULT_PORT = 17654

_DAEMON_CONFIG_PATH = config_dir() / "daemon.json"


@dataclass(frozen=True, slots=True)
class DaemonConfig:
    """The daemon's loopback port and bearer token."""

    port: int
    token: str


def _resolve_port() -> int:
    """Return the configured daemon port, from CLINE_HOOKS_DAEMON_PORT or the default."""
    raw = os.environ.get("CLINE_HOOKS_DAEMON_PORT")
    if not raw:
        return DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid CLINE_HOOKS_DAEMON_PORT %r; using default", raw)
        return DEFAULT_PORT


def _write(data: dict[str, Any]) -> None:
    """Atomically write the daemon config file at mode 0600."""
    _DAEMON_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=_DAEMON_CONFIG_PATH.parent)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    Path(tmp).replace(_DAEMON_CONFIG_PATH)


def try_load() -> DaemonConfig | None:
    """Read the daemon config file, without creating or writing it.

    Returns:
        The daemon's port and bearer token, or None if the file is absent,
        unreadable, or carries no usable port/token.
    """
    try:
        raw = json.loads(_DAEMON_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to read daemon config %s", _DAEMON_CONFIG_PATH)
        return None
    if not isinstance(raw, dict):
        return None
    port = raw.get("port")
    token = raw.get("token")
    if not isinstance(port, int) or not isinstance(token, str) or not token:
        return None
    return DaemonConfig(port=port, token=token)


def load_or_create() -> DaemonConfig:
    """Load the daemon config, creating it (with a fresh token) if absent.

    The port is re-resolved each call; an existing token is reused.

    Returns:
        The daemon's port and bearer token.
    """
    port = _resolve_port()
    existing = try_load()
    if existing is not None and existing.port == port:
        return existing
    daemon_config = DaemonConfig(port=port, token=existing.token if existing is not None else secrets.token_urlsafe(32))
    _write({"port": daemon_config.port, "token": daemon_config.token})
    return daemon_config
