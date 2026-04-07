from __future__ import annotations

import argparse
import logging
import sys
from typing import TYPE_CHECKING, NoReturn

from cline_hooks.frontends.cline import ClineProtocol, install_cline, parse_cline_data
from cline_hooks.frontends.kiro import KiroProtocol, install_kiro, parse_kiro_data
import cline_hooks.handlers  # noqa: F401
from cline_hooks.paths import get_data_dir
from cline_hooks.protocol import set_protocol
from cline_hooks.registry import HOOK_HANDLERS
from cline_hooks.response import allow

if TYPE_CHECKING:
    from cline_hooks.models import HookInput

logging.basicConfig(
    level=logging.DEBUG,
    filename=get_data_dir() / "cline-hooks.log",
    filemode="a",
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logging.getLogger("hooks").addHandler(logging.StreamHandler())

logger = logging.getLogger("hooks")


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Returns:
        The configured argument parser.
    """
    parser = argparse.ArgumentParser(prog="cline-hook", description="AI coding assistant lifecycle hooks")
    sub = parser.add_subparsers(dest="command")

    install_parser = sub.add_parser("install", help="Install hooks")
    install_sub = install_parser.add_subparsers(dest="install_mode")

    cline_parser = install_sub.add_parser("cline", help="Install Cline hooks (symlinks/scripts)")
    cline_parser.add_argument("target_dir", help="Directory to install hook entry points into")

    kiro_parser = install_sub.add_parser("kiro", help="Install Kiro hooks into agent config")
    kiro_parser.add_argument("agent_config", help="Path to Kiro agent config JSON file")

    return parser


def _detect_kiro(raw_data: str) -> bool:
    """Detect whether the input is from Kiro based on JSON shape.

    Args:
        raw_data: The raw JSON string from stdin.

    Returns:
        True if the input contains hook_event_name (Kiro format).
    """
    return '"hook_event_name"' in raw_data


def _parse_input(raw_data: str) -> HookInput:
    """Parse hook input, auto-detecting the frontend.

    Args:
        raw_data: The raw JSON string from stdin.

    Returns:
        A typed HookInput subclass.
    """
    if _detect_kiro(raw_data):
        set_protocol(KiroProtocol())
        return parse_kiro_data(raw_data)
    set_protocol(ClineProtocol())
    return parse_cline_data(raw_data)


def _run_hook() -> NoReturn:
    """Read hook input from stdin and dispatch to the appropriate handler."""
    try:
        hook = _parse_input(input())
    except Exception:
        logger.exception("Failed to parse hook input")
        allow()

    handler = HOOK_HANDLERS.get(hook.hookName)
    if handler is not None:
        handler(hook)

    allow()


def main() -> NoReturn:
    """Entrypoint - dispatches to install subcommands or hook processing."""
    args = _build_parser().parse_args()

    if args.command == "install":
        if args.install_mode == "kiro":
            install_kiro(args.agent_config)
        elif args.install_mode == "cline":
            install_cline(args.target_dir)
        else:
            _build_parser().parse_args(["install", "--help"])
        sys.exit(0)

    _run_hook()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Unexpected error", exc_info=e)
        raise
