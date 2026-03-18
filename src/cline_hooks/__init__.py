from __future__ import annotations

import logging
import sys
from typing import NoReturn

import cline_hooks.handlers  # noqa: F401
from cline_hooks.install import install
from cline_hooks.models import parse_data
from cline_hooks.paths import get_data_dir
from cline_hooks.registry import HOOK_HANDLERS
from cline_hooks.response import allow

logging.basicConfig(
    level=logging.DEBUG,
    filename=get_data_dir() / "cline-hooks.log",
    filemode="a",
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logging.getLogger("hooks").addHandler(logging.StreamHandler())

logger = logging.getLogger("hooks")


def main() -> NoReturn:
    """Busybox-style entrypoint - dispatches to a handler based on argv[0] basename."""
    if len(sys.argv) >= 2 and sys.argv[1] == "install":
        if len(sys.argv) < 3:
            print("Usage: cline-hook install <target-directory>", file=sys.stderr)
            sys.exit(1)
        install(sys.argv[2])
        sys.exit(0)

    try:
        hook = parse_data(input())
    except Exception:
        logger.exception("Failed to parse hook input")
        allow()

    handler = HOOK_HANDLERS.get(hook.hookName)
    if handler is not None:
        handler(hook)

    allow()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Unexpected error", exc_info=e)
        raise
