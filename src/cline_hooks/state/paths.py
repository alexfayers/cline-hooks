from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir


def get_data_dir() -> Path:
    """Return the platform data directory for cline-hooks state files."""
    data_dir = Path(user_data_dir("cline-hooks"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
