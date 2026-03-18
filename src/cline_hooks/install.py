from __future__ import annotations

import os
import sys
from pathlib import Path

_HOOKS = (
    "PreToolUse",
    "PostToolUse",
    "TaskStart",
    "TaskResume",
    "TaskCancel",
    "TaskComplete",
    "UserPromptSubmit",
    "PreCompact",
)


def install(target_dir: str) -> None:
    """Symlink all hook names to the cline-hook binary in target_dir.

    Args:
        target_dir: Directory to create hook symlinks in.
    """
    binary = Path(sys.executable).parent / "cline-hook"
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    linked = 0
    for hook in _HOOKS:
        dest = target / hook
        if dest.is_symlink() and os.readlink(dest) == str(binary):
            continue
        if dest.exists() and not dest.is_symlink():
            print(
                f"warning: {hook} exists but is not a symlink, skipping",
                file=sys.stderr,
            )
            continue
        dest.unlink(missing_ok=True)
        dest.symlink_to(binary)
        print(f"linked {hook}")
        linked += 1

    print(f"{linked} hooks linked.")
