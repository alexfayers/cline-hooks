from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir


def get_data_dir() -> Path:
    """Return the data directory for cline-hooks state files: `$CLINE_HOOKS_DATA_DIR`, else the platform default."""
    data_dir = Path(os.environ.get("CLINE_HOOKS_DATA_DIR") or user_data_dir("cline-hooks"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
