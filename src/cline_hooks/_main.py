from __future__ import annotations

import argparse
from contextvars import ContextVar
import logging
import sys
from typing import TYPE_CHECKING, NoReturn

from cline_hooks.core.dispatch import parse_hook, run_handler
from cline_hooks.core.frontends import FRONTENDS, FRONTENDS_BY_NAME
from cline_hooks.core.protocol import RawPayload
from cline_hooks.core.response import allow, render
import cline_hooks.handlers  # ruff: ignore[unused-import]
from cline_hooks.state.paths import get_data_dir

if TYPE_CHECKING:
    from cline_hooks.core.response import Response


class _InvocationContextFilter(logging.Filter):
    """Stamps every record with the current invocation's frontend and agent.

    Backed by a ContextVar per instance rather than plain attributes, so
    concurrent threads sharing one filter instance each see their own values.
    """

    def __init__(self) -> None:
        super().__init__()
        self._frontend: ContextVar[str] = ContextVar("frontend", default="-")
        self._agent: ContextVar[str] = ContextVar("agent", default="-")

    @property
    def frontend(self) -> str:
        """The current invocation's detected frontend name, or "-" if unknown."""
        return self._frontend.get()

    @frontend.setter
    def frontend(self, value: str) -> None:
        self._frontend.set(value)

    @property
    def agent(self) -> str:
        """The current invocation's agent type, or "-" if unknown."""
        return self._agent.get()

    @agent.setter
    def agent(self, value: str) -> None:
        self._agent.set(value)

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

    daemon_parser = sub.add_parser("daemon", help="Manage the loopback hook daemon")
    daemon_sub = daemon_parser.add_subparsers(dest="daemon_mode")
    daemon_sub.add_parser("serve", help="Run the daemon in the foreground")
    daemon_sub.add_parser("stop", help="Stop the running daemon")
    daemon_sub.add_parser("status", help="Check whether the daemon is running")

    service_parser = daemon_sub.add_parser(
        "service", help="Manage a login-time OS service that keeps the daemon running"
    )
    service_sub = service_parser.add_subparsers(dest="service_mode")
    service_sub.add_parser("install", help="Install and start a service that restarts the daemon on exit")
    service_sub.add_parser("uninstall", help="Remove the service, if cline-hooks installed it")
    service_sub.add_parser("status", help="Check whether the service is installed")
    service_sub.add_parser("stop", help="Stop the daemon through the service supervisor, so it stays stopped")

    return parser


def exit_with(response: Response) -> NoReturn:
    """Deliver a rendered Response via the command-path transport."""
    if response.stdout:
        print(response.stdout, end="")  # ruff: ignore[print]
    if response.stderr:
        print(response.stderr, end="", file=sys.stderr)  # ruff: ignore[print]
    sys.exit(response.exit_code)


def _run_hook() -> NoReturn:
    """Read hook input from stdin and dispatch to the appropriate handler."""
    logger.debug("=== start ===")
    try:
        payload = RawPayload.from_stdin(input())
        proto, hook = parse_hook(payload)
    except Exception:
        logger.exception("Failed to parse hook input")
        allow()

    _invocation_filter.frontend = proto.frontend_spec.name if proto.frontend_spec else "-"
    _invocation_filter.agent = hook.agentType or "main"

    outcome = run_handler(proto, hook)
    exit_with(render(outcome, proto))


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


def _cmd_install(args: argparse.Namespace) -> NoReturn:
    frontend = FRONTENDS_BY_NAME.get(args.install_mode or "")
    if frontend is None or frontend.installer is None:
        _build_parser().parse_args(["install", "--help"])
    else:
        argument = frontend.installer.argument
        target = getattr(args, argument.name) if argument is not None else None
        frontend.install(target)
    sys.exit(0)


def _cmd_plugins() -> NoReturn:
    _list_plugins()
    sys.exit(0)


def _cmd_retro_count(args: argparse.Namespace) -> NoReturn:
    from cline_hooks.state import retrospective  # ruff: ignore[import-outside-top-level]

    if args.reset:
        retrospective.reset()
    else:
        print(retrospective.get_count())  # ruff: ignore[print]
    sys.exit(0)


def _run_daemon_service(args: argparse.Namespace) -> None:
    from cline_hooks.daemon import service  # ruff: ignore[import-outside-top-level]

    if args.service_mode == "install":
        print(service.install())  # ruff: ignore[print]
    elif args.service_mode == "uninstall":
        print(service.uninstall())  # ruff: ignore[print]
    elif args.service_mode == "status":
        print(service.status())  # ruff: ignore[print]
    elif args.service_mode == "stop":
        print(service.stop())  # ruff: ignore[print]
    else:
        _build_parser().parse_args(["daemon", "service", "--help"])


def _cmd_daemon_service(args: argparse.Namespace) -> None:
    from cline_hooks.daemon import service  # ruff: ignore[import-outside-top-level]

    try:
        _run_daemon_service(args)
    except (service.UnsupportedPlatformError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)  # ruff: ignore[print]
        sys.exit(1)


def _cmd_daemon(args: argparse.Namespace) -> NoReturn:
    from cline_hooks.daemon import lifecycle  # ruff: ignore[import-outside-top-level]

    if args.daemon_mode == "serve":
        lifecycle.serve()
    elif args.daemon_mode == "stop":
        print(lifecycle.stop())  # ruff: ignore[print]
    elif args.daemon_mode == "status":
        print(lifecycle.status())  # ruff: ignore[print]
    elif args.daemon_mode == "service":
        _cmd_daemon_service(args)
    else:
        _build_parser().parse_args(["daemon", "--help"])
    sys.exit(0)


def main() -> NoReturn:
    """Entrypoint - dispatches to install subcommands or hook processing."""
    args = _build_parser().parse_args()

    if args.command == "install":
        _cmd_install(args)
    if args.command == "plugins":
        _cmd_plugins()
    if args.command == "retro-count":
        _cmd_retro_count(args)
    if args.command == "daemon":
        _cmd_daemon(args)

    _run_hook()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.exception("Unexpected error", exc_info=e)
        raise
