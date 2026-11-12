# ruff: file-ignore[print]
"""Locate binaries of the user-wide install, never those of a project virtual environment."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys

DEV_BIN_DIR_ENV = "CLINE_HOOKS_DEV_BIN_DIR"


def is_venv_scripts_dir(directory: Path) -> bool:
    """Report whether a directory holds the scripts of a virtual environment.

    Args:
        directory: A directory such as one from `PATH`.

    Returns:
        True where the directory (links followed) has a parent holding a `pyvenv.cfg`.
    """
    return (directory.resolve().parent / "pyvenv.cfg").exists()


def user_path(path: str | None = None) -> str:
    """Build a `PATH` without virtual environment scripts directories.

    Args:
        path: The `PATH` to filter, defaulting to the current one.

    Returns:
        The entries that are not virtual environment scripts directories, led by
        the directory named by `CLINE_HOOKS_DEV_BIN_DIR` where that is set.
    """
    entries = (os.environ.get("PATH", "") if path is None else path).split(os.pathsep)
    kept = [entry for entry in entries if entry and not is_venv_scripts_dir(Path(entry))]
    dev_dir = os.environ.get(DEV_BIN_DIR_ENV)
    return os.pathsep.join([dev_dir, *kept] if dev_dir else kept)


def resolve_user_binary(name: str) -> Path | None:
    """Find a binary of the user-wide install.

    Args:
        name: The binary's file name.

    Returns:
        The path as found on `PATH`, without resolving links, or None where absent.
        A binary found through `CLINE_HOOKS_DEV_BIN_DIR` is reported on stderr.
    """
    found = shutil.which(name, path=user_path())
    if not found:
        return None
    dev_dir = os.environ.get(DEV_BIN_DIR_ENV)
    if dev_dir and Path(found).parent == Path(dev_dir):
        print(f"warning: using {found} from {DEV_BIN_DIR_ENV}", file=sys.stderr)
    return Path(found)
