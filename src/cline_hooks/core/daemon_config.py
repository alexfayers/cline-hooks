"""The daemon's loopback port and bearer token, persisted alongside the user config."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import secrets
from typing import Any

from cline_hooks.config import config_dir

logger = logging.getLogger("hooks.daemon_config")

# Not checked against the live IANA registry - an inference, not a verified
# fact. Chosen to sit above 1024 (no privilege needed), below both Linux's
# (32768-60999) and macOS's (49152-65535) ephemeral ranges (so an unrelated
# outbound connection can't transiently steal it), and clear of common dev
# ports (3000/4000/5000/5432/6379/8000/8080/8888/9000 and neighbours).
# CLINE_HOOKS_DAEMON_PORT overrides this for anyone it collides with.
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


def _read_existing_token() -> str | None:
    """Return the token in the existing daemon config file, if any.

    Returns:
        The existing token, or None if the file is absent, unreadable, or
        carries no usable token.
    """
    try:
        raw = json.loads(_DAEMON_CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to read daemon config %s; regenerating", _DAEMON_CONFIG_PATH)
        return None
    token = raw.get("token") if isinstance(raw, dict) else None
    return token if isinstance(token, str) and token else None


def _write(data: dict[str, Any]) -> None:
    """Write the daemon config file at mode 0600."""
    _DAEMON_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DAEMON_CONFIG_PATH.write_text(json.dumps(data), encoding="utf-8")
    _DAEMON_CONFIG_PATH.chmod(0o600)


def try_load() -> DaemonConfig | None:
    """Read the daemon config file, without creating or writing it.

    Returns:
        The daemon's port and bearer token, or None if the file is absent,
        unreadable, or carries no usable port/token - callers on a
        fail-open path should treat that the same as an unreachable daemon.
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

    The port is always re-resolved from CLINE_HOOKS_DAEMON_PORT/the default;
    the token is reused from an existing file - regenerating it would break
    install idempotency and invalidate a running daemon.

    Returns:
        The daemon's port and bearer token.
    """
    port = _resolve_port()
    token = _read_existing_token() or secrets.token_urlsafe(32)
    _write({"port": port, "token": token})
    return DaemonConfig(port=port, token=token)
