from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import tomllib
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

from cline_hooks.core.frontend import FrontendSpec
from cline_hooks.core.frontends import FRONTENDS, FRONTENDS_BY_NAME
from cline_hooks.core.install import JsonHookInstaller, resolve_binary
import cline_hooks.daemon.config as daemon_config_module
from cline_hooks.daemon.config import load_or_create

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture

_FAKE_PYTHON = str(Path("/fake/bin/python"))
_EXPECTED_BINARY = str(Path(_FAKE_PYTHON).parent / "cline-hook")
_EXPECTED_GUARD_BINARY = str(Path(_FAKE_PYTHON).parent / "cline-hook-guard")


def _distribution_with_script(name: str) -> MagicMock:
    """Build a fake distribution exposing one console script.

    Returns:
        A stand-in for `importlib.metadata.distribution(...)`.
    """
    script = MagicMock(group="console_scripts")
    script.name = name
    return MagicMock(entry_points=[MagicMock(group="other"), script])


@contextmanager
def _patch_script_name(name: str) -> Iterator[None]:
    """Patch the installed distribution to declare a console script called `name`.

    Yields:
        Nothing; the patch holds for the duration of the context.
    """
    with patch("cline_hooks.core.install.distribution", return_value=_distribution_with_script(name)):
        yield


_JSON_FRONTENDS = [spec for spec in FRONTENDS if isinstance(spec.installer, JsonHookInstaller)]


def _declared_console_script(target: str) -> str:
    """Return the script name pyproject.toml's [project.scripts] declares for a target.

    Args:
        target: The `module:function` string as it appears in pyproject.toml.

    Returns:
        The script name.
    """
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    scripts = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"]["scripts"]
    for name, declared_target in scripts.items():
        if declared_target == target:
            return str(name)
    msg = f"No [project.scripts] entry points at {target!r}"
    raise AssertionError(msg)


def _installer(spec: FrontendSpec) -> JsonHookInstaller:
    """Return a spec's installer, narrowed to a JSON installer.

    Returns:
        The frontend's JsonHookInstaller.
    """
    assert isinstance(spec.installer, JsonHookInstaller)
    return spec.installer


def _target_for(spec: FrontendSpec, home: Path) -> str | None:
    """Return the install target for a frontend, where it takes one.

    Returns:
        A path inside `home`, or None where the install takes no argument.
    """
    installer = _installer(spec)
    if installer.argument is None:
        return None
    return str(home / f"{spec.name}-agent.json")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point Path.home(), the resolved binary, and the daemon config at a throwaway directory.

    Yields:
        The fake home directory.
    """
    monkeypatch.delenv("CLINE_HOOKS_DAEMON_PORT", raising=False)
    with (
        patch("cline_hooks.core.install.sys.executable", _FAKE_PYTHON),
        patch.object(Path, "home", return_value=tmp_path),
        patch.object(daemon_config_module, "_DAEMON_CONFIG_PATH", tmp_path / "daemon.json"),
        patch("cline_hooks.daemon.client.post_retire"),
    ):
        yield tmp_path


def _seed(spec: FrontendSpec, home: Path, config: dict[str, Any] | None = None) -> Path:
    """Write a starting config where the frontend requires an existing file.

    Args:
        spec: The frontend being installed.
        home: The fake home directory.
        config: Starting config content, defaulting to an empty object.

    Returns:
        The config path the installer will patch.
    """
    installer = _installer(spec)
    config_path = installer.config_path(_target_for(spec, home))
    if installer.must_exist or config is not None:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config or {}), encoding="utf-8")
    return config_path


def _install(spec: FrontendSpec, home: Path) -> dict[str, Any]:
    """Run a frontend's installer and read back the config it wrote.

    Returns:
        The parsed config file.
    """
    spec.install(_target_for(spec, home))
    config_path = _installer(spec).config_path(_target_for(spec, home))
    return dict(json.loads(config_path.read_text(encoding="utf-8")))


def _commands(spec: FrontendSpec, config: dict[str, Any], event: str) -> list[str]:
    """Return every command registered under one hook event.

    Returns:
        The commands in config order, as the installer itself reads them.
    """
    installer = _installer(spec)
    return [
        str(handler["command"])
        for entry in config[installer.root_key][event]
        for handler in installer.entry_handlers(entry)
    ]


def _first_event(spec: FrontendSpec) -> str:
    """Return the first hook event a frontend registers.

    Returns:
        The native event name.
    """
    return next(iter(spec.protocol.supported_hooks.values())).native_name


@pytest.mark.parametrize("spec", _JSON_FRONTENDS, ids=lambda spec: spec.name)
class TestJsonHookInstallers:
    """Invariants every JSON-configured frontend's installer must hold."""

    def test_installs_an_entry_for_every_registered_hook(self, spec: FrontendSpec, home: Path) -> None:
        _seed(spec, home)
        config = _install(spec, home)
        assert set(config[_installer(spec).root_key]) == {
            registration.native_name for registration in spec.protocol.supported_hooks.values()
        }

    def test_every_entry_runs_the_resolved_binary(self, spec: FrontendSpec, home: Path) -> None:
        _seed(spec, home)
        config = _install(spec, home)
        installer = _installer(spec)
        for entries in config[installer.root_key].values():
            for entry in entries:
                hooks = entry.get("hooks")
                candidates = hooks if isinstance(hooks, list) else [entry]
                for hook in candidates:
                    assert isinstance(hook, dict)
                    assert hook.get("command") in {_EXPECTED_BINARY, _EXPECTED_GUARD_BINARY}

    def test_preserves_unrelated_config_keys(self, spec: FrontendSpec, home: Path) -> None:
        _seed(spec, home, {"other": "value"})
        config = _install(spec, home)
        assert config["other"] == "value"
        assert _installer(spec).root_key in config

    def test_preserves_entries_from_other_sources(self, spec: FrontendSpec, home: Path) -> None:
        installer = _installer(spec)
        event = _first_event(spec)
        registration = next(iter(spec.protocol.supported_hooks.values()))
        foreign = installer.build_entry(Path("/other/tool"), registration)
        _seed(spec, home, {installer.root_key: {event: [foreign]}})

        config = _install(spec, home)
        commands = _commands(spec, config, event)
        assert "/other/tool" in commands
        assert _EXPECTED_BINARY in commands

    def test_idempotent_when_already_installed(self, spec: FrontendSpec, home: Path) -> None:
        _seed(spec, home)
        target = _target_for(spec, home)
        spec.install(target)
        config = _install(spec, home)
        event = _first_event(spec)
        assert _commands(spec, config, event).count(_EXPECTED_BINARY) == 1

    def test_rewrites_a_stale_cline_hook_path(self, spec: FrontendSpec, home: Path) -> None:
        installer = _installer(spec)
        event = _first_event(spec)
        registration = next(iter(spec.protocol.supported_hooks.values()))
        other_env = installer.build_entry(Path("/opt/other-env/bin/cline-hook"), registration)
        _seed(spec, home, {installer.root_key: {event: [other_env]}})

        config = _install(spec, home)
        assert _commands(spec, config, event) == [_EXPECTED_BINARY]

    def test_leaves_a_cline_hook_path_that_still_exists(self, spec: FrontendSpec, home: Path) -> None:
        installer = _installer(spec)
        event = _first_event(spec)
        registration = next(iter(spec.protocol.supported_hooks.values()))
        working = home / "other-env" / "cline-hook"
        working.parent.mkdir()
        working.write_text("", encoding="utf-8")
        _seed(spec, home, {installer.root_key: {event: [installer.build_entry(working, registration)]}})

        config = _install(spec, home)
        assert _commands(spec, config, event) == [str(working)]

    def test_force_rewrites_a_cline_hook_path_that_still_exists(self, spec: FrontendSpec, home: Path) -> None:
        installer = _installer(spec)
        event = _first_event(spec)
        registration = next(iter(spec.protocol.supported_hooks.values()))
        working = home / "other-env" / "cline-hook"
        working.parent.mkdir()
        working.write_text("", encoding="utf-8")
        config_path = _seed(spec, home, {installer.root_key: {event: [installer.build_entry(working, registration)]}})

        spec.install(_target_for(spec, home), force=True)
        config = json.loads(config_path.read_text(encoding="utf-8"))
        assert _commands(spec, config, event) == [_EXPECTED_BINARY]

    def test_rewrite_keeps_the_entry_s_other_fields(self, spec: FrontendSpec, home: Path) -> None:
        installer = _installer(spec)
        event = _first_event(spec)
        registration = next(iter(spec.protocol.supported_hooks.values()))
        stale = installer.build_entry(Path("/opt/other-env/bin/cline-hook"), registration)
        for handler in installer.entry_handlers(stale):
            handler["timeout"] = 5
        _seed(spec, home, {installer.root_key: {event: [stale]}})

        config = _install(spec, home)
        timeouts = [
            handler["timeout"]
            for entry in config[installer.root_key][event]
            for handler in installer.entry_handlers(entry)
        ]
        assert timeouts == [5]


class TestNestedEntryFrontends:
    """Claude Code and Codex share the nested "hook group" config shape."""

    @pytest.mark.parametrize("name", ["claude-code", "codex"])
    def test_tool_hooks_carry_their_matcher(self, name: str, home: Path) -> None:
        spec = FRONTENDS_BY_NAME[name]
        config = _install(spec, home)
        assert config["hooks"]["PreToolUse"][0]["matcher"] == ""
        assert config["hooks"]["PostToolUse"][0]["matcher"] == ""
        assert "matcher" not in config["hooks"]["SessionStart"][0]

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("claude-code", (".claude", "settings.json")),
            ("codex", (".codex", "hooks.json")),
            ("copilot", (".copilot", "hooks", "cline-hooks.json")),
        ],
    )
    def test_config_path(self, name: str, expected: tuple[str, ...], home: Path) -> None:
        spec = FRONTENDS_BY_NAME[name]
        assert _installer(spec).config_path(None) == home.joinpath(*expected)


class TestGuardHooks:
    """The four relayed hooks stay command entries, but must invoke the guard, not the full dispatch."""

    _GUARD_EVENTS = ("PreToolUse", "UserPromptSubmit", "PostToolUse", "Stop")

    @pytest.mark.parametrize("name", ["claude-code", "codex"])
    @pytest.mark.parametrize(
        ("event", "target"),
        [
            *((event, "cline_hooks.guard:main") for event in _GUARD_EVENTS),
            ("SessionStart", "cline_hooks._main:main"),
        ],
    )
    def test_command_matches_the_declared_console_script(self, name: str, event: str, target: str, home: Path) -> None:
        config = _install(FRONTENDS_BY_NAME[name], home)
        command = config["hooks"][event][0]["hooks"][0]["command"]
        assert Path(command).name == _declared_console_script(target)

    @pytest.mark.parametrize("name", ["claude-code", "codex"])
    @pytest.mark.parametrize("seeded_command", [_EXPECTED_BINARY, _EXPECTED_GUARD_BINARY])
    @pytest.mark.parametrize("event", _GUARD_EVENTS)
    def test_an_existing_entry_ends_as_one_guard_entry(
        self, name: str, event: str, seeded_command: str, home: Path
    ) -> None:
        spec = FRONTENDS_BY_NAME[name]
        old_entry = {"hooks": [{"type": "command", "command": seeded_command}]}
        _seed(spec, home, {_installer(spec).root_key: {event: [old_entry]}})
        config = _install(spec, home)
        assert [entry["hooks"][0]["command"] for entry in config["hooks"][event]] == [_EXPECTED_GUARD_BINARY]


class TestGuardFrontendsRetireTheDaemonAfterInstall:
    @pytest.mark.parametrize("name", ["claude-code", "pi", "codex", "copilot"])
    def test_posts_retire_to_the_local_daemon(
        self, name: str, home: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PI_CODING_AGENT_DIR", raising=False)
        retire = mocker.patch("cline_hooks.daemon.client.post_retire")
        FRONTENDS_BY_NAME[name].install()
        daemon_config = load_or_create()
        retire.assert_called_once_with(daemon_config.port, daemon_config.token)


class TestKiroInstaller:
    def test_entries_are_flat_and_described(self, home: Path) -> None:
        spec = FRONTENDS_BY_NAME["kiro"]
        _seed(spec, home, {"name": "test-agent", "tools": ["*"]})
        config = _install(spec, home)
        entry = config["hooks"]["preToolUse"][0]
        assert entry["command"] == _EXPECTED_BINARY
        assert entry["description"] == "cline-hooks preToolUse"
        assert entry["matcher"] == "*"
        assert "matcher" not in config["hooks"]["agentSpawn"][0]

    def test_preserves_the_rest_of_the_agent(self, home: Path) -> None:
        spec = FRONTENDS_BY_NAME["kiro"]
        _seed(spec, home, {"name": "my-agent", "description": "test", "tools": ["x"]})
        config = _install(spec, home)
        assert config["name"] == "my-agent"
        assert config["description"] == "test"
        assert config["tools"] == ["x"]

    def test_missing_agent_config_exits(self, home: Path, capsys: pytest.CaptureFixture[str]) -> None:
        spec = FRONTENDS_BY_NAME["kiro"]
        with pytest.raises(SystemExit) as excinfo:
            spec.install(str(home / "nope.json"))
        assert excinfo.value.code == 1
        assert "does not exist" in capsys.readouterr().err


class TestAntigravityInstaller:
    def test_entries_live_under_the_cline_hooks_hook_name(self, home: Path) -> None:
        spec = FRONTENDS_BY_NAME["antigravity"]
        _seed(spec, home, {"other-tool": {"PreToolUse": []}})
        config = _install(spec, home)
        assert set(config) == {"other-tool", "cline-hooks"}
        assert set(config["cline-hooks"]) == {"PreToolUse", "PostToolUse", "Stop"}

    def test_tool_events_are_hook_groups_behind_a_matcher(self, home: Path) -> None:
        spec = FRONTENDS_BY_NAME["antigravity"]
        config = _install(spec, home)
        for event in ("PreToolUse", "PostToolUse"):
            assert config["cline-hooks"][event] == [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": _EXPECTED_BINARY}],
                }
            ]

    def test_stop_entries_are_handlers_directly_under_the_event(self, home: Path) -> None:
        spec = FRONTENDS_BY_NAME["antigravity"]
        config = _install(spec, home)
        assert config["cline-hooks"]["Stop"] == [{"type": "command", "command": _EXPECTED_BINARY}]

    def test_reinstalling_leaves_the_flat_stop_entry_alone(self, home: Path) -> None:
        spec = FRONTENDS_BY_NAME["antigravity"]
        spec.install(None)
        config = _install(spec, home)
        assert config["cline-hooks"]["Stop"] == [{"type": "command", "command": _EXPECTED_BINARY}]


class TestCopilotInstaller:
    @pytest.mark.parametrize("event", ["UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"])
    def test_relayed_entries_are_flat_command_objects_on_the_guard(self, event: str, home: Path) -> None:
        config = _install(FRONTENDS_BY_NAME["copilot"], home)
        assert config["hooks"][event][0] == {"type": "command", "command": _EXPECTED_GUARD_BINARY}

    @pytest.mark.parametrize("event", ["SessionStart", "SubagentStop", "PreCompact"])
    def test_other_entries_are_flat_command_objects_on_the_full_dispatch(self, event: str, home: Path) -> None:
        config = _install(FRONTENDS_BY_NAME["copilot"], home)
        assert config["hooks"][event][0] == {"type": "command", "command": _EXPECTED_BINARY}


class TestResolveBinary:
    def test_prefers_an_existing_windows_executable(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "Scripts"
        scripts_dir.mkdir()
        exe = scripts_dir / "cline-hook.exe"
        exe.write_text("", encoding="utf-8")
        with patch("cline_hooks.core.install.sys.executable", str(scripts_dir / "python.exe")):
            assert resolve_binary() == exe

    def test_falls_back_to_the_unsuffixed_name(self, tmp_path: Path) -> None:
        with patch("cline_hooks.core.install.sys.executable", str(tmp_path / "python")):
            assert resolve_binary() == tmp_path / "cline-hook"

    def test_takes_the_name_from_the_distribution_console_script(self, tmp_path: Path) -> None:
        with (
            _patch_script_name("renamed-hook"),
            patch("cline_hooks.core.install.sys.executable", str(tmp_path / "python")),
        ):
            assert resolve_binary() == tmp_path / "renamed-hook"

    def test_prefers_an_existing_windows_executable_of_the_derived_name(self, tmp_path: Path) -> None:
        cmd = tmp_path / "renamed-hook.cmd"
        cmd.write_text("", encoding="utf-8")
        with (
            _patch_script_name("renamed-hook"),
            patch("cline_hooks.core.install.sys.executable", str(tmp_path / "python.exe")),
        ):
            assert resolve_binary() == cmd

    def test_prefers_the_path_link_to_the_running_binary(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        binary = scripts_dir / "cline-hook"
        binary.write_text("", encoding="utf-8")
        link = tmp_path / "bin" / "cline-hook"
        link.parent.mkdir()
        link.symlink_to(binary)
        with (
            patch("cline_hooks.core.install.sys.executable", str(scripts_dir / "python")),
            patch("cline_hooks.core.install.shutil.which", return_value=str(link)),
        ):
            assert resolve_binary() == link

    def test_ignores_a_path_binary_from_another_install(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "cline-hook").write_text("", encoding="utf-8")
        other = tmp_path / "other-cline-hook"
        other.write_text("", encoding="utf-8")
        with (
            patch("cline_hooks.core.install.sys.executable", str(scripts_dir / "python")),
            patch("cline_hooks.core.install.shutil.which", return_value=str(other)),
        ):
            assert resolve_binary() == scripts_dir / "cline-hook"


class TestEveryFrontendIsInstallable:
    def test_each_frontend_declares_an_installer(self) -> None:
        assert [spec.name for spec in FRONTENDS if spec.installer is None] == []

    def test_install_without_an_installer_is_refused(self) -> None:
        spec = FrontendSpec(
            name="no-install",
            display_name="No Install",
            protocol=FRONTENDS[0].protocol,
        )
        with pytest.raises(RuntimeError, match="no install step"):
            spec.install()
