"""The daemon's loopback HTTP client surface: /healthz probing and /admin/retire.

Stdlib only.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import URLError
import urllib.request

logger = logging.getLogger("hooks.daemon.client")

HEALTHZ_PATH = "/healthz"
RETIRE_PATH = "/admin/retire"
COMMAND_HOOK_PATH = "/hook/command"
ENV_FIELD = "cline_hooks_env"


def probe_healthz(port: int) -> dict[str, Any] | None:
    """Probe `GET /healthz` on `port`.

    Returns:
        The parsed healthz body if it looks like a cline-hooks daemon,
        otherwise None (nothing answered, or it answered something else).
    """
    try:
        url = f"http://127.0.0.1:{port}{HEALTHZ_PATH}"
        with urllib.request.urlopen(url, timeout=1) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (URLError, OSError, ValueError):
        return None
    if not isinstance(body, dict) or "plugin_fingerprint" not in body:
        return None
    return body


def post_retire(port: int, token: str) -> None:
    """POST `/admin/retire` on `port`, best-effort."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{RETIRE_PATH}",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=2):  # ruff: ignore[suspicious-url-open-usage]
            pass
    except (URLError, OSError):
        logger.warning("Failed to POST %s on port %d", RETIRE_PATH, port)
