from __future__ import annotations

import importlib.metadata
from importlib.metadata import version
import io
import json
import logging
import os
import pkgutil
import resource
import shutil
import signal
import subprocess
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

import cline_hooks
from cline_hooks._main import (
    _build_parser,
    _invocation_filter,
    _InvocationContextFilter,
    _run_hook,
    main,
)
from cline_hooks.config import _DEFAULT_MAX_MEMORY_MB
from cline_hooks.core.frontends import FRONTENDS, FRONTENDS_BY_NAME
from cline_hooks.core.install import binary_names
from cline_hooks.core.plugin import HookResult, HooksPlugin, collect_contributions, collect_hook_results, hookimpl
import cline_hooks.core.state as core_state_module
from cline_hooks.core.vocabulary import CanonicalHook
import cline_hooks.state.disabled_plugins as disabled_plugins_module
from tests.conftest import CanonicalProtocol, GreeterOwner, GreeterSpec

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from cline_hooks.core.frontend import FrontendSpec
    from cline_hooks.core.protocol import Protocol


def _run(
    payload: dict[str, object], env: dict[str, str] | None = None, protocol: type[Protocol] = CanonicalProtocol
) -> list[str]:
    """Feed one payload through the entry point and capture what it printed.

    Returns:
        Everything written to stdout, in order.
    """
    output: list[str] = []
    with (
        patch("sys.stdin", io.StringIO(json.dumps(payload))),
        patch("builtins.print", side_effect=lambda s, **kw: output.append(str(s))),
        patch.dict("os.environ", env or {}, clear=True),
        patch("cline_hooks._main.select_protocol", return_value=protocol),
        pytest.raises(SystemExit),
    ):
        _run_hook()
    return output


class TestHookDispatchGating:
    """A frontend only handles the hooks it declares."""

    def test_runs_a_hook_the_detected_frontend_fires(self) -> None:
        output = _run({
            "hookName": "TaskStart",
            "taskId": "task-1",
            "workspaceRoots": [],
            "taskStart": {"task": "", "source": "startup"},
        })
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
        output = _run(payload, protocol=claude_code)
        assert output == []

    def test_an_unknown_event_name_is_ignored(self) -> None:
        output = _run({"hookName": "SomethingElse", "taskId": "task-1", "workspaceRoots": []})
        assert json.loads(output[0])["cancel"] is False


_TASK_START_PAYLOAD: dict[str, object] = {
    "hookName": "TaskStart",
    "taskId": "task-1",
    "workspaceRoots": [],
    "taskStart": {"task": "", "source": "startup"},
}


class TestHookContext:
    def test_state_reads_and_writes_apply_to_the_payload_context(self) -> None:
        _run({**_TASK_START_PAYLOAD, "agentId": "agent-7", "anchorId": "e2", "contextAnchors": ["e1", "e2"]})
        assert core_state_module._context == core_state_module._HookContext(
            "task-1:agent-7", "e2", frozenset({"e1", "e2"})
        )


class TestInvocationContextFilter:
    """Every log record is stamped with the invocation's frontend and agent."""

    def test_defaults_agent_to_main_when_absent(self) -> None:
        _run(_TASK_START_PAYLOAD)
        assert _invocation_filter.agent == "main"

    def test_uses_the_payload_agent_type(self) -> None:
        _run({**_TASK_START_PAYLOAD, "agentType": "general-purpose"})
        assert _invocation_filter.agent == "general-purpose"

    def test_prefers_agent_id_over_agent_type(self) -> None:
        _run({**_TASK_START_PAYLOAD, "agentType": "general-purpose", "agentId": "agent-7"})
        assert _invocation_filter.agent == "agent-7"

    def test_uses_the_detected_frontends_name(self) -> None:
        payload: dict[str, object] = {
            "hook_event_name": "SessionStart",
            "session_id": "task-1",
            "cwd": "/workspace",
            "source": "startup",
        }
        _run(payload, protocol=FRONTENDS_BY_NAME["claude-code"].protocol)
        assert _invocation_filter.frontend == "claude-code"

    def test_context_omits_the_agent_when_main(self) -> None:
        context_filter = _InvocationContextFilter()
        context_filter.frontend = "claude-code"
        context_filter.agent = "main"
        record = logging.LogRecord("hooks", logging.INFO, __file__, 1, "msg", (), None)
        context_filter.filter(record)
        assert record.context == "claude-code"  # type: ignore[attr-defined]

    def test_context_includes_the_agent_when_not_main(self) -> None:
        context_filter = _InvocationContextFilter()
        context_filter.frontend = "claude-code"
        context_filter.agent = "general-purpose"
        record = logging.LogRecord("hooks", logging.INFO, __file__, 1, "msg", (), None)
        context_filter.filter(record)
        assert record.context == "claude-code/general-purpose"  # type: ignore[attr-defined]

    def test_context_is_just_a_dash_before_the_frontend_is_known(self) -> None:
        context_filter = _InvocationContextFilter()
        record = logging.LogRecord("hooks", logging.INFO, __file__, 1, "msg", (), None)
        context_filter.filter(record)
        assert record.context == "-"  # type: ignore[attr-defined]


_PRE_TOOL_USE_PAYLOAD: dict[str, object] = {
    "hookName": "PreToolUse",
    "taskId": "task-1",
    "workspaceRoots": [],
    "preToolUse": {"toolName": "execute_command", "parameters": {"command": "ls"}},
}
_MB = 1024 * 1024


def _run_under_cap(code: str) -> subprocess.CompletedProcess[str]:
    """Run Python code in a fresh process after the hook applies its default resource limits."""
    script = f"import subprocess\nfrom cline_hooks._main import _limit_resources\n_limit_resources()\n{code}"
    env = {key: value for key, value in os.environ.items() if key != "CLINE_HOOKS_MAX_MEMORY_MB"}
    return subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, check=False)


class ExhaustingPlugin(HooksPlugin):
    """Runs `exhaust` on every hook, standing in for a plugin that runs out of a resource."""

    def __init__(self, exhaust: Callable[[], object]) -> None:
        super().__init__()
        self.exhaust = exhaust

    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        self.exhaust()
        return None


def _raise_memory_error() -> None:
    raise MemoryError


@pytest.fixture
def setrlimit() -> Iterator[MagicMock]:
    """Record the hook's resource limits instead of applying them to the test process."""
    cpu_handler = signal.getsignal(signal.SIGXCPU)
    with patch("resource.setrlimit") as recorded, patch.dict("os.environ"):
        yield recorded
    signal.signal(signal.SIGXCPU, cpu_handler)


def _run_main(payload: dict[str, object]) -> list[str]:
    """Feed one payload through `main` as the hook command, and capture what it printed.

    Returns:
        Everything written to stdout, in order.
    """
    output: list[str] = []
    with (
        patch("sys.argv", ["cline-hook"]),
        patch("sys.stdin", io.StringIO(json.dumps(payload))),
        patch("builtins.print", side_effect=lambda s, **kw: output.append(str(s))),
        patch("cline_hooks._main.select_protocol", return_value=CanonicalProtocol),
        pytest.raises(SystemExit),
    ):
        main()
    return output


class TestResourceLimits:
    """A hook that runs out of memory, CPU time or payload room allows the tool call."""

    @pytest.mark.usefixtures("setrlimit")
    @pytest.mark.parametrize(
        "exhaust", [_raise_memory_error, lambda: signal.raise_signal(signal.SIGXCPU)], ids=["memory", "cpu"]
    )
    def test_running_out_allows_the_tool_call_with_a_warning(
        self, exhaust: Callable[[], object], use_plugins: Callable[..., None], caplog: pytest.LogCaptureFixture
    ) -> None:
        use_plugins(ExhaustingPlugin(exhaust))
        with caplog.at_level(logging.WARNING, logger="hooks"):
            output = _run_main(_PRE_TOOL_USE_PAYLOAD)
        assert json.loads(output[0])["cancel"] is False
        assert any(
            record.levelno == logging.WARNING and "PreToolUse" in record.message and "execute_command" in record.message
            for record in caplog.records
        )

    @pytest.mark.parametrize(("env", "megabytes"), [({}, 640), ({"CLINE_HOOKS_MAX_MEMORY_MB": "512"}, 512)])
    def test_caps_the_data_segment_at_the_configured_size(
        self, setrlimit: MagicMock, monkeypatch: pytest.MonkeyPatch, env: dict[str, str], megabytes: int
    ) -> None:
        monkeypatch.delenv("CLINE_HOOKS_MAX_MEMORY_MB", raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        _run_main(_TASK_START_PAYLOAD)
        limits = {call.args[0]: call.args[1][0] for call in setrlimit.call_args_list}
        assert limits[resource.RLIMIT_DATA] == megabytes * _MB
        assert resource.RLIMIT_CPU in limits

    def test_runs_uncapped_where_the_os_rejects_a_memory_cap(self, setrlimit: MagicMock) -> None:
        def reject_memory_cap(limit: int, _values: tuple[int, int]) -> None:
            if limit == resource.RLIMIT_DATA:
                raise ValueError("current limit exceeds maximum limit")

        setrlimit.side_effect = reject_memory_cap
        _run_main(_TASK_START_PAYLOAD)
        assert resource.RLIMIT_CPU in {call.args[0] for call in setrlimit.call_args_list}

    @pytest.mark.skipif(sys.platform != "linux", reason="the memory cap is enforced on Linux only")
    @pytest.mark.parametrize("command", [["gh", "--version"], ["node", "--version"]], ids=["go", "node"])
    def test_a_child_with_a_large_virtual_reserve_starts_under_the_cap(self, command: list[str]) -> None:
        if not shutil.which(command[0]):
            pytest.skip(f"{command[0]} is not installed")
        assert _run_under_cap(f"subprocess.run({command!r}, check=True, capture_output=True)").returncode == 0

    @pytest.mark.skipif(sys.platform != "linux", reason="the memory cap is enforced on Linux only")
    def test_an_allocation_over_the_cap_fails(self) -> None:
        completed = _run_under_cap(f"bytearray({2 * _DEFAULT_MAX_MEMORY_MB} * {_MB})")
        assert "MemoryError" in completed.stderr

    @pytest.mark.usefixtures("setrlimit")
    def test_git_children_map_pack_files_within_the_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLINE_HOOKS_MAX_MEMORY_MB", "400")
        _run_main(_TASK_START_PAYLOAD)
        completed = subprocess.run(
            ["git", "config", "--get", "core.packedGitLimit"],  # ruff: ignore[start-process-with-partial-path]
            capture_output=True,
            text=True,
            check=True,
        )
        assert completed.stdout.strip() == "100m"

    @pytest.mark.usefixtures("setrlimit")
    def test_a_payload_over_the_size_cap_is_allowed_unread(
        self, use_plugins: Callable[..., None], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        use_plugins(ExhaustingPlugin(_raise_memory_error))
        monkeypatch.setattr("cline_hooks._main._MAX_PAYLOAD_CHARS", len(json.dumps(_PRE_TOOL_USE_PAYLOAD)) - 1)
        monkeypatch.setattr("cline_hooks.core.protocol._active_protocol", None)
        with caplog.at_level(logging.WARNING, logger="hooks"):
            output = _run_main(_PRE_TOOL_USE_PAYLOAD)
        assert json.loads(output[0])["cancel"] is False
        assert not any("PreToolUse" in record.message for record in caplog.records)
        assert any(record.levelno == logging.WARNING for record in caplog.records)


_IMPORT_PACKAGE = """
import logging
before = list(logging.root.handlers)
import cline_hooks
print(logging.root.handlers == before)
"""

_IMPORT_LOADS_CLI = """
import sys
import cline_hooks
print("cline_hooks._main" in sys.modules)
"""


class TestImportSideEffects:
    def test_importing_the_package_leaves_root_logging_unchanged(self) -> None:
        out = subprocess.run([sys.executable, "-c", _IMPORT_PACKAGE], capture_output=True, text=True, check=True)
        assert out.stdout.strip() == "True"

    def test_importing_the_package_does_not_import_the_cli(self) -> None:
        out = subprocess.run([sys.executable, "-c", _IMPORT_LOADS_CLI], capture_output=True, text=True, check=True)
        assert out.stdout.strip() == "False"

    def test_every_module_imports_in_a_fresh_interpreter(self) -> None:
        runs = {
            name: subprocess.Popen([sys.executable, "-c", f"import {name}"], stderr=subprocess.PIPE, text=True)
            for _, name, _ in pkgutil.walk_packages(cline_hooks.__path__, "cline_hooks.")
        }
        errors = {name: run.communicate()[1] for name, run in runs.items()}
        failed = {name: errors[name] for name, run in runs.items() if run.returncode}
        assert not failed, "\n".join(failed.values())


class TestParserProgramName:
    def test_is_the_distribution_console_script_name(self) -> None:
        with patch("cline_hooks._main.binary_names", return_value=("renamed-hook", "renamed-hook.exe")):
            assert _build_parser().prog == "renamed-hook"


class TestInstallSubcommands:
    """The CLI is generated from the registry, so it never names a frontend."""

    @pytest.mark.parametrize("spec", FRONTENDS, ids=lambda spec: spec.name)
    def test_every_frontend_has_a_subcommand(self, spec: FrontendSpec) -> None:
        parser = _build_parser()
        args = parser.parse_args(
            ["install", spec.name]
            + (["some-target"] if spec.installer is not None and spec.installer.argument is not None else [])
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
        assert install.call_args.kwargs == {"force": False}

    @pytest.mark.parametrize("spec", FRONTENDS, ids=lambda spec: spec.name)
    def test_force_flag_is_passed_to_the_installer(self, spec: FrontendSpec) -> None:
        installer = spec.installer
        assert installer is not None
        argv = ["cline-hook", "install", spec.name, "--force"]
        if installer.argument is not None:
            argv.append("/tmp/target")

        with (
            patch.object(type(installer), "install") as install,
            patch("sys.argv", argv),
            pytest.raises(SystemExit),
        ):
            main()

        assert install.call_args.kwargs == {"force": True}

    def test_unknown_install_mode_prints_help(self) -> None:
        with (
            patch("sys.argv", ["cline-hook", "install"]),
            pytest.raises(SystemExit),
        ):
            main()


class Greeter(HooksPlugin):
    @hookimpl
    def greetings(self, name: str) -> list[str]:
        return [f"hello {name}"]


class StrayContributor(HooksPlugin):
    @hookimpl
    def unpublished_extension_point(self) -> list[str]:
        return []


def test_version_flag_prints_the_installed_version(capsys: pytest.CaptureFixture[str]) -> None:
    prog = binary_names()[0]
    with patch("sys.argv", [prog, "--version"]), pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    assert capsys.readouterr().out == f"{prog} {version('cline-hooks')}\n"


def _plugins_output(capsys: pytest.CaptureFixture[str]) -> str:
    with patch("sys.argv", ["cline-hook", "plugins"]), pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0
    return capsys.readouterr().out


class TestListPlugins:
    def test_reports_the_check_pending_failure_naming_the_plugin(
        self, use_plugins: Callable[..., None], capsys: pytest.CaptureFixture[str]
    ) -> None:
        use_plugins(GreeterOwner(), Greeter(), StrayContributor())

        output = _plugins_output(capsys)

        assert "greetings" in output
        assert "check_pending" in output
        assert "clean" not in output
        assert "unpublished_extension_point" in output
        assert StrayContributor.__name__ in output

    @pytest.mark.usefixtures("fresh_plugin_cache")
    def test_exits_non_zero_naming_a_plugin_that_failed_to_load(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        entry_point = importlib.metadata.EntryPoint("missing", "fakeep_missing:MissingPlugin", "cline_hooks")
        monkeypatch.setattr(importlib.metadata, "entry_points", lambda **_kwargs: (entry_point,))

        with patch("sys.argv", ["cline-hook", "plugins"]), pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 1
        assert "External plugin missing failed to load" in capsys.readouterr().err


class Talker(HooksPlugin):
    def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
        return HookResult(notes=[f"talker saw {hook_name}"])


def _run_plugins_verb(*args: str) -> None:
    with patch("sys.argv", ["cline-hook", "plugins", *args]), pytest.raises(SystemExit) as excinfo:
        main()
    assert excinfo.value.code == 0


class TestPluginToggles:
    def test_a_disabled_plugin_emits_nothing_until_re_enabled(
        self, use_plugins: Callable[..., None], capsys: pytest.CaptureFixture[str]
    ) -> None:
        use_plugins(Talker())

        _run_plugins_verb("--disable", "Talker", "--reason", "too noisy")

        assert collect_hook_results([Talker()], "TaskStart").notes == []
        assert "disabled: too noisy" in _plugins_output(capsys)

        _run_plugins_verb("--enable", "Talker")

        assert collect_hook_results([Talker()], "TaskStart").notes == ["talker saw TaskStart"]
        assert "enabled" in _plugins_output(capsys)

    def test_a_disabled_plugin_contributes_nothing_to_extension_points(self, use_plugins: Callable[..., None]) -> None:
        use_plugins(GreeterOwner(), Greeter())

        _run_plugins_verb("--disable", "Greeter")

        assert collect_contributions(GreeterSpec.greetings, list, name="Ada") == []

    @pytest.mark.parametrize("content", ["null", '{"Talker": "x"}', '{"Talker": {"at": 1}}', "[]"])
    def test_a_malformed_state_file_leaves_every_plugin_enabled(
        self, use_plugins: Callable[..., None], capsys: pytest.CaptureFixture[str], content: str
    ) -> None:
        use_plugins(Talker())
        disabled_plugins_module._STATE_PATH.write_text(content)

        assert collect_hook_results([Talker()], "TaskStart").notes == ["talker saw TaskStart"]
        assert "state:           enabled" in _plugins_output(capsys)

    @pytest.mark.usefixtures("setrlimit")
    def test_a_hook_run_from_stdin_skips_a_disabled_plugin(self, use_plugins: Callable[..., None]) -> None:
        use_plugins(Talker())
        assert any("talker saw TaskStart" in line for line in _run_main(_TASK_START_PAYLOAD))

        _run_plugins_verb("--disable", "Talker")

        assert not any("talker saw" in line for line in _run_main(_TASK_START_PAYLOAD))

    @pytest.mark.parametrize("content", ["null", "[]", '{"Talker": "x"}'])
    def test_disable_and_enable_repair_a_malformed_state_file(
        self, use_plugins: Callable[..., None], content: str
    ) -> None:
        use_plugins(Talker())
        disabled_plugins_module._STATE_PATH.write_text(content)

        _run_plugins_verb("--disable", "Talker")
        assert set(json.loads(disabled_plugins_module._STATE_PATH.read_text())) == {"Talker"}

        disabled_plugins_module._STATE_PATH.write_text(content)
        _run_plugins_verb("--enable", "Talker")
        assert json.loads(disabled_plugins_module._STATE_PATH.read_text()) == {}

    def test_names_match_case_insensitively(self, use_plugins: Callable[..., None]) -> None:
        use_plugins(Talker())

        _run_plugins_verb("--disable", "talker")

        assert collect_hook_results([Talker()], "TaskStart").notes == []

    def test_enable_removes_an_entry_whose_plugin_is_gone(self, use_plugins: Callable[..., None]) -> None:
        use_plugins(Talker())
        disabled_plugins_module.disable("RemovedPlugin")

        _run_plugins_verb("--enable", "removedplugin")

        assert disabled_plugins_module.disabled_plugins() == {}

    def test_an_unknown_plugin_name_is_rejected(self, use_plugins: Callable[..., None]) -> None:
        use_plugins(Talker())

        with patch("sys.argv", ["cline-hook", "plugins", "--disable", "Nope"]), pytest.raises(SystemExit) as excinfo:
            main()

        assert excinfo.value.code == 2
