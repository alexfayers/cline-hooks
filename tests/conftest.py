from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import sys
from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.frontends import DEFAULT_PROTOCOL
from cline_hooks.core.plugin import HooksPlugin, _plugin_cache, hookspec, plugins_override
from cline_hooks.core.protocol import get_protocol, set_protocol
from cline_hooks.core.transcript import TranscriptReader
import cline_hooks.plugins.context_usage as context_usage_module
import cline_hooks.plugins.delegation as delegation_module
import cline_hooks.plugins.nudges as nudges_module
import cline_hooks.plugins.plan_handoff as plan_handoff_module
import cline_hooks.plugins.research as research_module
import cline_hooks.state.agents as agents_tracker_module
import cline_hooks.state.memory as memory_tracker_module
import cline_hooks.state.retrospective as retrospective_module
import cline_hooks.state.skills as skill_tracker_module
import cline_hooks.state.store as state_store_module
import cline_hooks.state.workspace as workspace_module

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from pytest_mock import MockerFixture


@dataclass
class StubTranscript(TranscriptReader):
    """A scriptable transcript reader that answers empty without a path."""

    tokens: int | None = None
    text: str = ""
    subagent_tokens: int | None = None
    subagent_report_text: str = ""

    def context_tokens(self, transcript_path: str) -> int | None:
        """Return the scripted token count.

        Returns:
            The scripted count when a transcript is named, otherwise None.
        """
        return self.tokens if transcript_path else None

    def turn_assistant_text(self, transcript_path: str) -> str:
        """Return the scripted assistant text.

        Returns:
            The scripted text when a transcript is named, otherwise "".
        """
        return self.text if transcript_path else ""

    def subagent_context_tokens(self, transcript_path: str, agent_id: str) -> int | None:
        """Return the scripted subagent token count.

        Returns:
            The scripted count when a transcript and agent id are named,
            otherwise None.
        """
        return self.subagent_tokens if transcript_path and agent_id else None

    def subagent_report(self, transcript_path: str, agent_id: str) -> str:
        """Return the scripted subagent report.

        Returns:
            The scripted report when a transcript and agent id are named,
            otherwise "".
        """
        return self.subagent_report_text if transcript_path and agent_id else ""


@pytest.fixture
def stub_transcript(
    mocker: MockerFixture,
) -> Callable[..., StubTranscript]:
    """Swap the active protocol's transcript reader for a scripted stub.

    Returns:
        A callable taking `tokens`, `text`, `subagent_tokens` and/or
        `subagent_report_text` that installs the stub.
    """

    def install(
        *,
        tokens: int | None = None,
        text: str = "",
        subagent_tokens: int | None = None,
        subagent_report_text: str = "",
    ) -> StubTranscript:
        stub = StubTranscript(
            tokens=tokens,
            text=text,
            subagent_tokens=subagent_tokens,
            subagent_report_text=subagent_report_text,
        )
        mocker.patch.object(type(get_protocol()), "transcript", stub)
        return stub

    return install


@pytest.fixture
def use_plugins() -> Iterator[Callable[..., None]]:
    """Restrict plugin loading to the given plugins for the rest of the test.

    Yields:
        A callable taking the plugins to install.
    """
    with ExitStack() as stack:

        def install(*plugins: HooksPlugin) -> None:
            stack.enter_context(plugins_override(plugins))

        yield install


FAKE_PLUGIN_PREFIX = "fakeep_"


@pytest.fixture
def fresh_plugin_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Reset the plugin cache around a test that imports fake plugin modules from tmp_path."""
    monkeypatch.syspath_prepend(str(tmp_path))
    _plugin_cache._loaded = None
    yield
    _plugin_cache._loaded = None
    for name in [name for name in sys.modules if name.startswith(FAKE_PLUGIN_PREFIX)]:
        del sys.modules[name]


class GreeterSpec:
    @hookspec
    def greetings(self, name: str) -> list[str]:
        """Greet someone by name."""
        raise NotImplementedError


class GreeterOwner(HooksPlugin):
    hookspecs = GreeterSpec


@pytest.fixture(autouse=True, scope="session")
def isolate_log_file(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Redirect the "hooks" logger away from the real, shared log file.

    cline_hooks._main configures logging.basicConfig at import time against the
    real user log file; without this, running the test suite writes deliberate
    test-triggered tracebacks into the same log live hook invocations use.
    """
    log_path = tmp_path_factory.mktemp("logs") / "cline-hooks.log"
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    root_logger.addHandler(logging.FileHandler(log_path))


@pytest.fixture(autouse=True)
def isolate_state_files(mocker: MockerFixture, tmp_path: Path) -> None:
    """Redirect all state file paths to tmp_path and set default protocol."""
    mocker.patch.object(state_store_module, "_STATE_PATH", tmp_path / "hook-state.json")
    mocker.patch.object(skill_tracker_module, "_STATE_PATH", tmp_path / "skill-state.json")
    mocker.patch.object(memory_tracker_module, "_STATE_PATH", tmp_path / "memory-state.json")
    mocker.patch.object(retrospective_module, "_STATE_PATH", tmp_path / "retrospective-state.json")
    mocker.patch.object(nudges_module._store, "_path", tmp_path / "turns-state.json")
    mocker.patch.object(agents_tracker_module, "_STATE_PATH", tmp_path / "agents-state.json")
    mocker.patch.object(context_usage_module._store, "_path", tmp_path / "context-state.json")
    mocker.patch.object(plan_handoff_module._store, "_path", tmp_path / "plan-state.json")
    mocker.patch.object(research_module._store, "_path", tmp_path / "research-state.json")
    mocker.patch.object(workspace_module, "_STATE_PATH", tmp_path / "workspace-state.json")
    mocker.patch.object(delegation_module._store, "_path", tmp_path / "delegation-state.json")
    mocker.patch.dict(os.environ, {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": ""})
    set_protocol(DEFAULT_PROTOCOL())


FAKE_HOME = Path("/fake/home")


@pytest.fixture
def fake_home(monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home directory that does not exist on disk, exported as HOME.

    Returns:
        The fake home path.
    """
    monkeypatch.setenv("HOME", str(FAKE_HOME))
    return FAKE_HOME


@dataclass
class FakeDirEntry:
    """A directory entry as returned by os.scandir."""

    name: str
    path: str
    is_directory: bool = False
    is_symlink: bool = False

    def is_dir(self, *, follow_symlinks: bool = True) -> bool:
        """Report whether the entry is a directory, as os.DirEntry.is_dir does.

        Returns:
            True for a directory, unless it is a symlink and symlinks are not followed.
        """
        return self.is_directory and (follow_symlinks or not self.is_symlink)


@dataclass
class FakeFilesystem:
    """An in-memory directory tree served through the patched os.scandir and Path.read_text."""

    listings: dict[str, list[FakeDirEntry]] = field(default_factory=dict)
    gitignores: dict[str, str] = field(default_factory=dict)
    unreadable: set[str] = field(default_factory=set)

    def add_files(self, directory: str, count: int) -> str:
        """Add `count` files to a directory, creating it when missing.

        Returns:
            The directory path.
        """
        entries = self.listings.setdefault(directory, [])
        for _ in range(count):
            name = f"file{len(entries)}.txt"
            entries.append(FakeDirEntry(name, f"{directory}/{name}"))
        return directory

    def add_directory(self, parent: str, name: str, *, symlink: bool = False) -> str:
        """Add an empty subdirectory, creating the parent when missing.

        Returns:
            The subdirectory path.
        """
        path = f"{parent}/{name}"
        self.listings.setdefault(parent, []).append(FakeDirEntry(name, path, is_directory=True, is_symlink=symlink))
        self.listings.setdefault(path, [])
        return path

    def scandir(self, path: str) -> Iterator[FakeDirEntry]:
        """List a directory, as os.scandir does.

        Returns:
            An iterator over the directory's entries.

        Raises:
            PermissionError: If the directory is marked unreadable.
            FileNotFoundError: If the directory does not exist.
        """
        if path in self.unreadable:
            raise PermissionError(path)
        if path not in self.listings:
            raise FileNotFoundError(path)
        return iter(self.listings[path])

    def read_text(self, path: Path, **_: str) -> str:
        """Read a .gitignore, as Path.read_text does.

        Returns:
            The registered file contents.

        Raises:
            FileNotFoundError: If no contents are registered for the path.
        """
        if str(path) not in self.gitignores:
            raise FileNotFoundError(path)
        return self.gitignores[str(path)]


@pytest.fixture
def fake_filesystem(mocker: MockerFixture) -> FakeFilesystem:
    """Serve directory listings and file reads from an in-memory tree.

    Returns:
        The tree to populate.
    """
    filesystem = FakeFilesystem()
    mocker.patch("os.scandir", side_effect=filesystem.scandir)
    mocker.patch.object(Path, "read_text", autospec=True, side_effect=filesystem.read_text)
    return filesystem
