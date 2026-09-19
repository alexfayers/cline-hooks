"""Lock-guarded, atomic read-modify-write access to shared JSON state files."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def read_json[StateT](path: Path, default: StateT) -> StateT:
    """Read a JSON state file, returning the default on a missing or corrupt file.

    Args:
        path: The state file path.
        default: A freshly constructed value to return when the file is unusable.

    Returns:
        The parsed file contents, or the default.
    """
    try:
        return cast("StateT", json.loads(path.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError, OSError):
        return default


@contextmanager
def updated_json[StateT](path: Path, default: StateT) -> Iterator[StateT]:
    """Yield a state file's contents under an exclusive lock, writing them back on exit.

    The lock is held across the read, the caller's mutation and the atomic write, so
    concurrent processes cannot lose an update or publish a partial file.

    Args:
        path: The state file path.
        default: A freshly constructed value to yield when the file is unusable.

    Yields:
        The parsed file contents, mutated in place by the caller.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        data = read_json(path, default)
        yield data
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(path)


def discard_key(path: Path, key: str) -> None:
    """Remove a top-level key from a JSON state file, leaving a missing key untouched.

    The presence check runs before the lock, so clearing an absent key creates no
    file and takes no lock. The removal itself still happens under the lock, so a
    concurrent update cannot be lost.

    Args:
        path: The state file path.
        key: The top-level key to remove.
    """
    if key not in read_json(path, cast("dict[str, object]", {})):
        return
    with updated_json(path, cast("dict[str, object]", {})) as data:
        data.pop(key, None)
