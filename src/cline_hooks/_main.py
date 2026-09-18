from __future__ import annotations

import argparse
import logging
import sys
from typing import TYPE_CHECKING, NoReturn

from cline_hooks.core.frontends import FRONTENDS, FRONTENDS_BY_NAME, select_protocol
from cline_hooks.core.protocol import Protocol, RawPayload, set_protocol
from cline_hooks.core.registry import HOOK_HANDLERS
from cline_hooks.core.response import allow, emit
import cline_hooks.handlers  # ruff: ignore[unused-import]
from cline_hooks.state.paths import get_data_dir

if TYPE_CHECKING:
    from cline_hooks.core.models import HookInput


class _InvocationContextFilter(logging.Filter):
    """Stamps every record with the current invocation's frontend and agent."""

    def __init__(self) -> None:
        super().__init__()
        self.frontend = "-"
        self.agent = "-"

    def filter(self, record: logging.LogRecord) -> bool:
        """Attach the current invocation context to the record and always allow it through.

        Returns:
            True, unconditionally.
        """
        if self.frontend == "-" or self.agent == "main":
            record.context = self.frontend
        else:
            record.context = f"{self.frontend}/{self.agent}"
        return True


_invocation_filter = _InvocationContextFilter()

logging.basicConfig(
    level=logging.DEBUG,
    filename=get_data_dir() / "cline-hooks.log",
    filemode="a",
    format="%(asctime)s %(levelname)s %(name)s[%(context)s]: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logging.root.handlers[0].addFilter(_invocation_filter)

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

    for frontend in FRONTENDS:
        installer = frontend.installer
        if installer is None:
            continue
        frontend_parser = install_sub.add_parser(frontend.name, help=installer.help)
        if installer.argument is not None:
            frontend_parser.add_argument(installer.argument.name, help=installer.argument.help)

    sub.add_parser("plugins", help="List installed plugins")

    retro_parser = sub.add_parser("retro-count", help="Read or reset the retrospective session counter")
    retro_group = retro_parser.add_mutually_exclusive_group(required=True)
    retro_group.add_argument("--get", action="store_true", help="Print the current session count")
    retro_group.add_argument("--reset", action="store_true", help="Reset the session count to zero")

    return parser


def _parse_hook(payload: RawPayload) -> tuple[Protocol, HookInput]:
    """Detect the frontend, configure logging for it, and parse the payload.

    Returns:
        The detected protocol and the parsed hook input.
    """
    proto = select_protocol(payload).from_payload(payload)
    set_protocol(proto)
    proto.configure_logging()
    hook = proto.parse(payload)
    _invocation_filter.frontend = proto.frontend_spec.name if proto.frontend_spec else "-"
    _invocation_filter.agent = hook.agentType or "main"
    return proto, hook


def _run_hook() -> NoReturn:
    """Read hook input from stdin and dispatch to the appropriate handler."""
    logger.debug("=== start ===")
    try:
        payload = RawPayload.from_stdin(input())
        proto, hook = _parse_hook(payload)
    except Exception:
        logger.exception("Failed to parse hook input")
        allow()

    if not proto.fires(hook.hookName):
        logger.debug("Ignoring %s: not a hook %s fires", hook.hookName, type(proto).__name__)
        allow()

    handler = HOOK_HANDLERS.get(hook.hookName)
    if handler is not None:
        outcome = handler(hook)
        if outcome is not None:
            emit(outcome)

    allow()


def _list_plugins() -> None:
    """Print all loaded plugins and their capabilities."""
    from cline_hooks.core.plugin import (  # ruff: ignore[import-outside-top-level]
        HooksPlugin,
        list_plugin_methods,
        load_plugins,
    )

    plugins = load_plugins()
    if not plugins:
        print("No plugins loaded.")  # ruff: ignore[print]
        return

    method_names = [info.name for info in list_plugin_methods()]

    for plugin in plugins:
        name = type(plugin).__name__
        module = type(plugin).__module__
        build_cmds = plugin.get_build_commands()
        rules = plugin.get_command_rules()
        overrides = [
            method_name
            for method_name in method_names
            if getattr(plugin, method_name).__func__ is not getattr(HooksPlugin, method_name)
        ]
        print(f"{name} ({module})")  # ruff: ignore[print]
        if build_cmds:
            print(f"  build commands: {', '.join(sorted(build_cmds))}")  # ruff: ignore[print]
        if rules:
            print(f"  command rules:  {len(rules)}")  # ruff: ignore[print]
        print(f"  overrides:      {', '.join(overrides) if overrides else 'none'}")  # ruff: ignore[print]


def main() -> NoReturn:
    """Entrypoint - dispatches to install subcommands or hook processing."""
    args = _build_parser().parse_args()

    if args.command == "install":
        frontend = FRONTENDS_BY_NAME.get(args.install_mode or "")
        if frontend is None or frontend.installer is None:
            _build_parser().parse_args(["install", "--help"])
        else:
            argument = frontend.installer.argument
            target = getattr(args, argument.name) if argument is not None else None
            frontend.install(target)
        sys.exit(0)

    if args.command == "plugins":
        _list_plugins()
        sys.exit(0)

    if args.command == "retro-count":
        from cline_hooks.state import retrospective  # ruff: ignore[import-outside-top-level]

        if args.reset:
            retrospective.reset()
        else:
            print(retrospective.get_count())  # ruff: ignore[print]
        sys.exit(0)

    _run_hook()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Unexpected error", exc_info=e)
        raise
