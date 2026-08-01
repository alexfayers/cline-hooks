from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import TYPE_CHECKING, NoReturn

from cline_hooks.core.protocol import set_protocol
from cline_hooks.core.registry import HOOK_HANDLERS
from cline_hooks.core.response import allow
from cline_hooks.frontends.claude_code import ClaudeCodeProtocol, install_claude_code
from cline_hooks.frontends.cline import ClineProtocol, install_cline, parse_cline_data
from cline_hooks.frontends.codex import install_codex
from cline_hooks.frontends.copilot import install_copilot
from cline_hooks.frontends.kiro import KiroProtocol, install_kiro, parse_kiro_data
import cline_hooks.handlers  # noqa: F401
from cline_hooks.state.paths import get_data_dir

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInput

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
    parser = argparse.ArgumentParser(prog="cline-hook", description="AI coding assistant lifecycle hooks")
    sub = parser.add_subparsers(dest="command")

    install_parser = sub.add_parser("install", help="Install hooks")
    install_sub = install_parser.add_subparsers(dest="install_mode")

    cline_parser = install_sub.add_parser("cline", help="Install Cline hooks (symlinks/scripts)")
    cline_parser.add_argument("target_dir", help="Directory to install hook entry points into")

    kiro_parser = install_sub.add_parser("kiro", help="Install Kiro hooks into agent config")
    kiro_parser.add_argument("agent_config", help="Path to Kiro agent config JSON file")

    install_sub.add_parser("claude-code", help="Install Claude Code hooks into settings")
    install_sub.add_parser("codex", help="Install Codex hooks into hooks.json")
    install_sub.add_parser("copilot", help="Install GitHub Copilot hooks into ~/.copilot/hooks/")

    sub.add_parser("plugins", help="List installed plugins")

    retro_parser = sub.add_parser("retro-count", help="Read or reset the retrospective session counter")
    retro_group = retro_parser.add_mutually_exclusive_group(required=True)
    retro_group.add_argument("--get", action="store_true", help="Print the current session count")
    retro_group.add_argument("--reset", action="store_true", help="Reset the session count to zero")

    return parser


def _detect_kiro(raw_data: str) -> bool:
    """Detect whether the input is from Kiro based on JSON shape.

    Args:
        raw_data: The raw JSON string from stdin.

    Returns:
        True if hook_event_name is a top-level key (Kiro format).
    """
    try:
        data = json.loads(raw_data)
    except (json.JSONDecodeError, ValueError):
        return False
    return isinstance(data, dict) and "hook_event_name" in data


def _detect_claude_code(raw_data: str) -> bool:
    """Detect whether Kiro-shaped input is actually from Claude Code.

    Claude Code's hook_event_name values are PascalCase (Stop, SessionStart);
    Kiro's are lowercase/camelCase (stop, agentSpawn). Verified against every
    event each frontend actually registers (frontends/*/install.py) - zero
    overlap.

    Args:
        raw_data: The raw JSON string from stdin.

    Returns:
        True if the hook_event_name is PascalCase (Claude Code).
    """
    try:
        data = json.loads(raw_data)
    except (json.JSONDecodeError, ValueError):
        return False
    name = data.get("hook_event_name") if isinstance(data, dict) else None
    return isinstance(name, str) and name[:1].isupper()


def _parse_input(raw_data: str) -> HookInput:
    """Parse hook input, auto-detecting the frontend.

    Args:
        raw_data: The raw JSON string from stdin.

    Returns:
        A typed HookInput subclass.
    """
    if _detect_kiro(raw_data):
        if _detect_claude_code(raw_data):
            hook_event_name = json.loads(raw_data).get("hook_event_name", "")
            set_protocol(ClaudeCodeProtocol(hook_event_name))
        else:
            set_protocol(KiroProtocol())
        return parse_kiro_data(raw_data)
    logging.getLogger("hooks").addHandler(logging.StreamHandler())
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
