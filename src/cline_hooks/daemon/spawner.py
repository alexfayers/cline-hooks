"""Start the daemon as a detached process."""

from __future__ import annotations

import subprocess
import sys

from cline_hooks.state.paths import get_data_dir


def spawn() -> None:
    """Start the daemon detached from the current process, redirecting its stdio to a log file."""
    log_path = get_data_dir() / "daemon.log"
    with log_path.open("a", encoding="utf-8") as log_file:
        subprocess.Popen(
            [sys.executable, "-m", "cline_hooks", "daemon", "serve"],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
