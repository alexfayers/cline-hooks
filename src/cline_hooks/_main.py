from __future__ import annotations

import argparse
from contextvars import ContextVar
import logging
import sys
from typing import NoReturn

from cline_hooks.core.dispatch import parse_hook, run_handler
from cline_hooks.core.frontends import FRONTENDS, FRONTENDS_BY_NAME
from cline_hooks.core.install import binary_names
from cline_hooks.core.protocol import RawPayload
from cline_hooks.core.response import Response, render
import cline_hooks.handlers  # ruff: ignore[unused-import]
from cline_hooks.state.paths import get_data_dir


class _InvocationContextFilter(logging.Filter):
    """Stamps every record with the current invocation's frontend and agent."""

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
    parser = argparse.ArgumentParser(prog=binary_names()[0], description="AI coding assistant lifecycle hooks")
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
        exit_with(Response())

    _invocation_filter.frontend = proto.frontend_spec.name if proto.frontend_spec else "-"
    _invocation_filter.agent = hook.agentId or hook.agentType or "main"

    outcome = run_handler(proto, hook)
    exit_with(render(outcome, proto))


def _list_plugins() -> None:
    """Print all loaded plugins and their capabilities."""
    import pluggy  # ruff: ignore[import-outside-top-level]

    from cline_hooks.core.plugin import (  # ruff: ignore[import-outside-top-level]
        HooksPlugin,
        get_plugin_manager,
        list_extension_points,
        load_plugins,
    )

    plugins = load_plugins()
    if not plugins:
        print("No plugins loaded.")  # ruff: ignore[print]
        return

    manager = get_plugin_manager()
    extension_points = list_extension_points(plugins)

    for plugin in plugins:
        name = type(plugin).__name__
        owned = [
            f"{point.name}({point.params}) -> {point.return_type}: {point.purpose}"
            for point in extension_points
            if point.owner == name
        ]
        contributions = sorted(caller.name for caller in manager.get_hookcallers(plugin) or [])
        overrides_on_hook = type(plugin).on_hook is not HooksPlugin.on_hook
        print(f"{name} ({type(plugin).__module__})")  # ruff: ignore[print]
        print("  extension points:")  # ruff: ignore[print]
        for line in owned or ["none"]:
            print(f"    {line}")  # ruff: ignore[print]
        print(f"  contributes to:  {', '.join(contributions) if contributions else 'none'}")  # ruff: ignore[print]
        print(f"  on_hook:         {'overridden' if overrides_on_hook else 'not overridden'}")  # ruff: ignore[print]

    try:
        manager.check_pending()
    except pluggy.PluginValidationError as error:
        print(f"check_pending: failed - {error}")  # ruff: ignore[print]
    else:
        print("check_pending: clean")  # ruff: ignore[print]


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
