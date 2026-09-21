"""PreToolUse thin client: ask the daemon for the decision, allow if unreachable.

Deliberately import-light - this runs on the hot path of every guarded tool
call, so importing it must never pull in `cline_hooks.handlers`,
`cline_hooks.plugins`, or any frontend protocol class. Only stdlib plus the
daemon's port/token config and the `/hook/command` path constant.

The daemon owns every rendering decision; this module replays its
exit_code/stdout/stderr verbatim and never substitutes its own judgement.
Any failure to get a usable answer - no daemon config, connection refused,
a bad status, an unparseable or malformed body - allows silently on stdout,
logging the failure so a silently-unenforced guard is still discoverable.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import NoReturn
from urllib.error import URLError
import urllib.request

from cline_hooks.core.daemon_config import try_load
from cline_hooks.daemon.client import COMMAND_HOOK_PATH
from cline_hooks.state.paths import get_data_dir

logger = logging.getLogger("hooks.thin_client")


def _select_timeout(raw: str) -> int:
    """Pick the per-event timeout: 2s for PreToolUse, 5s for everything else.

    PreToolUse blocks the tool call, so a stalled daemon must be bounded
    tightly. Every other relayed hook isn't blocking a tool call the same
    way, so it gets 5s - matching the old native-http registration's timeout.

    Args:
        raw: The raw stdin string, not yet known to be valid JSON.

    Returns:
        2 if the parsed body is a dict with `hook_event_name == "PreToolUse"`,
        otherwise 5.
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return 5
    if not isinstance(parsed, dict):
        return 5
    return 2 if parsed.get("hook_event_name") == "PreToolUse" else 5


def _configure_logging() -> None:
    """Route this module's logger to its own file - never stdout, the hook's response channel."""
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


def main() -> NoReturn:
    """Ask the daemon for PreToolUse's decision and replay it verbatim, or allow."""
    _configure_logging()
    raw = sys.stdin.read()
    timeout_seconds = _select_timeout(raw)

    daemon_config = try_load()
    if daemon_config is None:
        _allow("No daemon config found")

    request = urllib.request.Request(
        f"http://127.0.0.1:{daemon_config.port}{COMMAND_HOOK_PATH}",
        data=raw.encode("utf-8"),
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
