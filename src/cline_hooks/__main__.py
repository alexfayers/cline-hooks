"""The `cline-hook` command, which runs `serve` before it imports the hook code."""

import sys
from typing import NoReturn


def main() -> NoReturn:
    """Run `serve` and `serve --stop` from the hook server module alone, and every other command from `_main`."""
    if sys.argv[1:] in (["serve"], ["serve", "--stop"]):
        from cline_hooks import server  # ruff: ignore[import-outside-top-level]

        sys.exit(server.stop() if sys.argv[2:] else server.serve())
    from cline_hooks._main import main as hook_main  # ruff: ignore[import-outside-top-level]

    hook_main()


if __name__ == "__main__":
    main()
