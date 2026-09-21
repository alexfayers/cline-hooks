"""Hook thin client: relay a hook event to the daemon for the decision, allow if unreachable.

Replays the daemon's exit_code/stdout/stderr verbatim;
any failure to get a usable answer is logged and allowed.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import NoReturn
from urllib.error import URLError
import urllib.request

from cline_hooks.core.daemon_config import try_load
from cline_hooks.daemon import service
from cline_hooks.daemon.client import COMMAND_HOOK_PATH, ENV_FIELD
from cline_hooks.daemon.spawner import spawn
from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks.thin_client")

_GUARD_TIMEOUT_SECONDS = 2
_POST_TOOL_USE_TIMEOUT_SECONDS = 35
_DEFAULT_TIMEOUT_SECONDS = 5


def _select_timeout(raw: str) -> int:
    """Pick the per-event timeout: 2s for PreToolUse, 35s for PostToolUse, 5s for everything else.

    Args:
        raw: The raw stdin string, not yet known to be valid JSON.

    Returns:
        2 if the parsed body is a dict with `hook_event_name == "PreToolUse"`,
        35 if it is "PostToolUse", otherwise 5.
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return _DEFAULT_TIMEOUT_SECONDS
    if not isinstance(parsed, dict):
        return _DEFAULT_TIMEOUT_SECONDS
    return {"PreToolUse": _GUARD_TIMEOUT_SECONDS, "PostToolUse": _POST_TOOL_USE_TIMEOUT_SECONDS}.get(
        str(parsed.get("hook_event_name")), _DEFAULT_TIMEOUT_SECONDS
    )


def _with_env(raw: str) -> str:
    """Add this process's environment to the hook payload under `ENV_FIELD`.

    Args:
        raw: The raw stdin string, not yet known to be valid JSON.

    Returns:
        The payload re-serialized with the environment added, or `raw` unchanged if it isn't a JSON object.
    """
    try:
        parsed = json.loads(raw)
    except ValueError:
        return raw
    if not isinstance(parsed, dict):
        return raw
    parsed[ENV_FIELD] = dict(os.environ)
    return json.dumps(parsed)


def _configure_logging() -> None:
    """Route this module's logger to its own file."""
    if logger.handlers:
        return
    handler = logging.FileHandler(get_data_dir() / "cline-hooks-guard.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False


def _allow(reason: str) -> NoReturn:
    """Exit 0 with no output, after logging why."""
    logger.warning("%s; allowing", reason)
    sys.exit(0)


def _nothing_listening(exc: Exception) -> bool:
    """Check whether a failure means the daemon's port refused the connection.

    Returns:
        True if `exc` or its `reason` is a `ConnectionRefusedError`.
    """
    return isinstance(exc, ConnectionRefusedError) or isinstance(getattr(exc, "reason", None), ConnectionRefusedError)


def _respawn() -> None:
    """Start the daemon, logging instead of raising if it cannot be started."""
    try:
        spawn()
    except OSError as exc:
        logger.warning("Failed to respawn the daemon (%s)", exc)


def main() -> NoReturn:
    """Ask the daemon for the hook event's decision and replay it verbatim, or allow."""
    _configure_logging()
    raw = sys.stdin.read()
    timeout_seconds = _select_timeout(raw)

    daemon_config = try_load()
    if daemon_config is None:
        _allow("No daemon config found")

    request = urllib.request.Request(
        f"http://127.0.0.1:{daemon_config.port}{COMMAND_HOOK_PATH}",
        data=_with_env(raw).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {daemon_config.token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # ruff: ignore[suspicious-url-open-usage]
            body = json.loads(response.read().decode("utf-8"))
    except (URLError, OSError, ValueError) as exc:
        if _nothing_listening(exc) and not service.is_installed():
            _respawn()
        _allow(f"Failed to get a usable answer from the daemon ({exc})")

    if not isinstance(body, dict):
        _allow("Daemon response was not a JSON object")

    exit_code = body.get("exit_code")
    stdout = body.get("stdout")
    stderr = body.get("stderr")
    if not isinstance(exit_code, int) or not isinstance(stdout, str) or not isinstance(stderr, str):
        _allow("Daemon response was missing an expected field")

    if stdout:
        sys.stdout.write(stdout)
    if stderr:
        sys.stderr.write(stderr)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
