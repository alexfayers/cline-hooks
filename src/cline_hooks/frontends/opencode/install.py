"""Opencode's install paths."""

from __future__ import annotations

import os
from pathlib import Path


def config_dir() -> Path:
    """Return opencode's global config directory, as opencode resolves it.

    Returns:
        `$OPENCODE_CONFIG_DIR`, else `$XDG_CONFIG_HOME/opencode`, else
        `~/.config/opencode`.
    """
    if override := os.environ.get("OPENCODE_CONFIG_DIR"):
        return Path(override).expanduser()
    if xdg := os.environ.get("XDG_CONFIG_HOME"):
        return Path(xdg).expanduser() / "opencode"
    return Path.home() / ".config" / "opencode"
