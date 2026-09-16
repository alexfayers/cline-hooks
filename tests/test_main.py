from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from cline_hooks._main import _build_parser, _list_plugins, _run_hook, main
from cline_hooks.core.frontends import FRONTENDS, FRONTENDS_BY_NAME
from cline_hooks.core.vocabulary import CanonicalHook

if TYPE_CHECKING:
    from cline_hooks.core.frontend import FrontendSpec


def _run(payload: dict[str, object], env: dict[str, str] | None = None) -> list[str]:
    """Feed one payload through the entry point and capture what it printed.

    Returns:
        Everything written to stdout, in order.
    """
    output: list[str] = []
    with (
        patch("builtins.input", return_value=json.dumps(payload)),
        patch("builtins.print", side_effect=lambda s, **kw: output.append(str(s))),
        patch.dict("os.environ", env or {}, clear=True),
        pytest.raises(SystemExit),
    ):
        _run_hook()
    return output


class TestHookDispatchGating:
    """A frontend only handles the hooks it declares."""

    def test_runs_a_hook_the_detected_frontend_fires(self) -> None:
        output = _run(
            {
                "hookName": "TaskStart",
                "taskId": "task-1",
                "workspaceRoots": [],
                "taskStart": {"task": "", "source": "startup"},
            }
        )
        assert json.loads(output[0])["cancel"] is False

    def test_ignores_a_hook_the_detected_frontend_does_not_fire(self) -> None:
        """Claude Code has no PreCompact, so a PreCompact it routed must no-op."""
        claude_code = FRONTENDS_BY_NAME["claude-code"].protocol
        assert CanonicalHook.PRE_COMPACT not in claude_code.supported_hooks

        payload = {
            "hook_event_name": "PreCompact",
            "session_id": "task-1",
            "cwd": "/workspace",
            "conversation_length": 10,
            "estimated_tokens": 1000,
        }
        with patch(
            "cline_hooks._main.select_protocol", return_value=claude_code
        ) as select:
            output = _run(payload)
        assert select.called
        assert output == []

    def test_an_unknown_event_name_is_ignored(self) -> None:
        output = _run(
            {"hookName": "SomethingElse", "taskId": "task-1", "workspaceRoots": []}
        )
        assert json.loads(output[0])["cancel"] is False


class TestInstallSubcommands:
    """The CLI is generated from the registry, so it never names a frontend."""

    @pytest.mark.parametrize("spec", FRONTENDS, ids=lambda spec: spec.name)
    def test_every_frontend_has_a_subcommand(self, spec: FrontendSpec) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            ["install", spec.name]
            + (
                ["some-target"]
                if spec.installer is not None and spec.installer.argument is not None
                else []
            )
        )
        assert args.install_mode == spec.name

    @pytest.mark.parametrize("spec", FRONTENDS, ids=lambda spec: spec.name)
    def test_install_dispatches_to_the_frontend(self, spec: FrontendSpec) -> None:
        installer = spec.installer
        assert installer is not None
        argv = ["cline-hook", "install", spec.name]
        if installer.argument is not None:
            argv.append("/tmp/target")

        with (
            patch.object(type(installer), "install") as install,
            patch("sys.argv", argv),
            pytest.raises(SystemExit) as excinfo,
        ):
            main()

        assert excinfo.value.code == 0
        install.assert_called_once()
        called_protocol, called_target = install.call_args.args
        assert called_protocol is spec.protocol
        assert called_target == ("/tmp/target" if installer.argument else None)

    def test_unknown_install_mode_prints_help(self) -> None:
        with (
            patch("sys.argv", ["cline-hook", "install"]),
            pytest.raises(SystemExit),
        ):
            main()


class TestListPlugins:
    def test_reports_overridden_methods(self) -> None:
        from cline_hooks.core.plugin import HookResult, HooksPlugin

        class _Plugin(HooksPlugin):
            def get_build_commands(self) -> frozenset[str]:
                return frozenset({"make"})

            def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
                return None

        output: list[str] = []
        with (
            patch("cline_hooks.core.plugin.load_plugins", return_value=[_Plugin()]),
            patch("builtins.print", side_effect=lambda s, **kw: output.append(str(s))),
        ):
            _list_plugins()
        overrides_line = next(line for line in output if "overrides:" in line)
        assert "get_build_commands" in overrides_line
        assert "on_hook" in overrides_line
        assert "get_command_rules" not in overrides_line

    def test_no_overrides_says_none_rather_than_nothing(self) -> None:
        from cline_hooks.core.plugin import HooksPlugin

        output: list[str] = []
        with (
            patch("cline_hooks.core.plugin.load_plugins", return_value=[HooksPlugin()]),
            patch("builtins.print", side_effect=lambda s, **kw: output.append(str(s))),
        ):
            _list_plugins()
        overrides_line = next(line for line in output if "overrides:" in line)
        assert "none" in overrides_line
