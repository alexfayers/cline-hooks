from __future__ import annotations

import argparse
import logging
import sys
from typing import NoReturn

from cline_hooks.core.frontends import select_protocol
from cline_hooks.core.protocol import RawPayload, set_protocol
from cline_hooks.core.registry import HOOK_HANDLERS
from cline_hooks.core.response import allow, emit
from cline_hooks.frontends.claude_code import install_claude_code
from cline_hooks.frontends.cline import install_cline
from cline_hooks.frontends.codex import install_codex
from cline_hooks.frontends.copilot import install_copilot
from cline_hooks.frontends.kiro import install_kiro
import cline_hooks.handlers  # noqa: F401
from cline_hooks.state.paths import get_data_dir

logging.basicConfig(
    level=logging.DEBUG,
    filename=get_data_dir() / "cline-hooks.log",
    filemode="a",
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

logger = logging.getLogger("hooks")


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Returns:
        The configured argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="cline-hook", description="AI coding assistant lifecycle hooks"
    )
    sub = parser.add_subparsers(dest="command")

    install_parser = sub.add_parser("install", help="Install hooks")
    install_sub = install_parser.add_subparsers(dest="install_mode")

    cline_parser = install_sub.add_parser(
        "cline", help="Install Cline hooks (symlinks/scripts)"
    )
    cline_parser.add_argument(
        "target_dir", help="Directory to install hook entry points into"
    )

    kiro_parser = install_sub.add_parser(
        "kiro", help="Install Kiro hooks into agent config"
    )
    kiro_parser.add_argument("agent_config", help="Path to Kiro agent config JSON file")

    install_sub.add_parser(
        "claude-code", help="Install Claude Code hooks into settings"
    )
    install_sub.add_parser("codex", help="Install Codex hooks into hooks.json")
    install_sub.add_parser(
        "copilot", help="Install GitHub Copilot hooks into ~/.copilot/hooks/"
    )

    sub.add_parser("plugins", help="List installed plugins")

    retro_parser = sub.add_parser(
        "retro-count", help="Read or reset the retrospective session counter"
    )
    retro_group = retro_parser.add_mutually_exclusive_group(required=True)
    retro_group.add_argument(
        "--get", action="store_true", help="Print the current session count"
    )
    retro_group.add_argument(
        "--reset", action="store_true", help="Reset the session count to zero"
    )

    return parser


def _run_hook() -> NoReturn:
    """Read hook input from stdin and dispatch to the appropriate handler."""
    try:
        payload = RawPayload.from_stdin(input())
        proto = select_protocol(payload).from_payload(payload)
        set_protocol(proto)
        proto.configure_logging()
        hook = proto.parse(payload)
    except Exception:
        logger.exception("Failed to parse hook input")
        allow()

    handler = HOOK_HANDLERS.get(hook.hookName)
    if handler is not None:
        outcome = handler(hook)
        if outcome is not None:
            emit(outcome)

    allow()


def _list_plugins() -> None:
    """Print all loaded plugins and their capabilities."""
    from cline_hooks.core.plugin import load_plugins  # noqa: PLC0415

    plugins = load_plugins()
    if not plugins:
        print("No plugins loaded.")  # noqa: T201
        return

    for plugin in plugins:
        name = type(plugin).__name__
        module = type(plugin).__module__
        build_cmds = plugin.get_build_commands()
        rules = plugin.get_command_rules()
        print(f"{name} ({module})")  # noqa: T201
        if build_cmds:
            print(f"  build commands: {', '.join(sorted(build_cmds))}")  # noqa: T201
        if rules:
            print(f"  command rules:  {len(rules)}")  # noqa: T201


def main() -> NoReturn:
    """Entrypoint - dispatches to install subcommands or hook processing."""
    args = _build_parser().parse_args()

    if args.command == "install":
        if args.install_mode == "kiro":
            install_kiro(args.agent_config)
        elif args.install_mode == "cline":
            install_cline(args.target_dir)
        elif args.install_mode == "claude-code":
            install_claude_code()
        elif args.install_mode == "codex":
            install_codex()
        elif args.install_mode == "copilot":
            install_copilot()
        else:
            _build_parser().parse_args(["install", "--help"])
        sys.exit(0)

    if args.command == "plugins":
        _list_plugins()
        sys.exit(0)

    if args.command == "retro-count":
        from cline_hooks.state import retrospective  # noqa: PLC0415

        if args.reset:
            retrospective.reset()
        else:
            print(retrospective.get_count())  # noqa: T201
        sys.exit(0)

    _run_hook()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Unexpected error", exc_info=e)
        raise
