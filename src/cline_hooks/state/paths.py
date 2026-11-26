from __future__ import annotations

import logging
import os
from pathlib import Path

from platformdirs import user_data_dir

from cline_hooks.state.path_migration import migrate
from cline_hooks.state.tool_paths import root, tool_dir

logger = logging.getLogger("hooks.state.paths")

_TOOL = "cline-hooks"
_KIND = "state"


def _shared_state_dir() -> Path:
    """Return the state folder under the shared root, or the old data directory while the copy to it fails.

    The files of the old data directory are copied once, and the old files stay in place.
    """
    old = Path(user_data_dir(_TOOL))
    new = tool_dir(_TOOL, _KIND)
    copies = [(child, new / child.name) for child in sorted(old.iterdir())] if old.is_dir() else []
    try:
        failures = migrate(root() / _TOOL, copies)
    except OSError as error:
        failures = {_KIND: str(error)}
    if failures:
        logger.warning("could not copy %s to %s, using the old folder: %s", old, new, failures[_KIND])
        return old
    return new


def get_data_dir() -> Path:
    """Return the data directory for cline-hooks state files: `$CLINE_HOOKS_DATA_DIR`, else under the shared root."""
    override = os.environ.get("CLINE_HOOKS_DATA_DIR")
    data_dir = Path(override) if override else _shared_state_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
