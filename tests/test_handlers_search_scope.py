from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import TYPE_CHECKING

import bashlex
import pytest

from cline_hooks.handlers import search_scope as search_scope_module
from cline_hooks.handlers.commands import extract_commands
from cline_hooks.handlers.search_scope import (
    SearchScope,
    effective_cwd,
    find_oversized_search,
    is_home_or_above,
    search_scope,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture

    from tests.conftest import FakeDirEntry, FakeFilesystem

CWD = "/w"
SMALL_CAP = 10
BIG = SMALL_CAP * 2
TREE = "/fake/tree"


@pytest.fixture
def small_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(search_scope_module, "MAX_SCAN_ENTRIES", SMALL_CAP)


def _oversized(command: str, session_cwd: Path | str = CWD) -> SearchScope | None:
    return find_oversized_search(extract_commands(bashlex.parse(command)), str(session_cwd))


def _scope(command: str, cwd: str = CWD) -> SearchScope | None:
    return search_scope(extract_commands(bashlex.parse(command))[0], cwd)


class TestSearchScope:
    @pytest.mark.parametrize("command", ["grep foo file", "git grep foo", "ls -R"])
    def test_non_recursive_search_has_no_scope(self, command: str) -> None:
        assert _scope(command) is None

    @pytest.mark.parametrize(
        ("command", "roots"),
        [
            ("grep -rn foo src", ("/w/src",)),
            ("grep -R foo", ("/w",)),
            ("grep --recursive -e foo a b", ("/w/a", "/w/b")),
            ("grep -r -A 3 foo src", ("/w/src",)),
            ("grep -d recurse foo src", ("/w/src",)),
            ("grep --directories=recurse foo src", ("/w/src",)),
            ("rg foo", ("/w",)),
            ("rg -g '*.py' -t py foo src", ("/w/src",)),
            ("rg foo src/*.py", ("/w/src",)),
            ("fd -e py foo src", ("/w/src",)),
            ("find . -name '*.py'", ("/w",)),
            ("find / -name x", ("/",)),
            ("find a b -name x", ("/w/a", "/w/b")),
            ("find -name x", ("/w",)),
        ],
    )
    def test_roots(self, command: str, roots: tuple[str, ...]) -> None:
        scope = _scope(command)
        assert scope is not None
        assert scope.roots == roots

    @pytest.mark.parametrize(
        ("command", "depth"),
        [
            ("rg --max-depth=1 foo", 1),
            ("rg --max-depth 2 foo", 2),
            ("rg -d3 foo", 3),
            ("fd -d 2 foo", 2),
            ("fd --exact-depth 4 foo", 4),
            ("find . -maxdepth 1 -type d", 1),
            ("ag --depth 2 foo", 2),
            ("ag --depth=5 foo", 5),
            ("rg --max-depth x foo", None),
            ("rg foo", None),
        ],
    )
    def test_max_depth(self, command: str, depth: int | None) -> None:
        scope = _scope(command)
        assert scope is not None
        assert scope.max_depth == depth

    @pytest.mark.parametrize(
        ("command", "respects"),
        [
            ("rg foo", True),
            ("rg -uu foo src", False),
            ("rg --hidden foo", False),
            ("fd -H foo", False),
            ("fd foo", True),
            ("grep -r foo", False),
            ("find . -name x", False),
        ],
    )
    def test_respects_ignores(self, command: str, respects: bool) -> None:
        scope = _scope(command)
        assert scope is not None
        assert scope.respects_ignores is respects

    def test_expands_home_and_variables(self, fake_home: Path) -> None:
        assert _scope("rg --max-depth 2 foo ~") == SearchScope("rg", (str(fake_home),), 2, True)
        assert _scope('rg foo "$HOME"') == SearchScope("rg", (str(fake_home),), None, True)
        assert _scope("rg foo ${HOME}/a") == SearchScope("rg", (f"{fake_home}/a",), None, True)
        assert _scope("fd -d 2 foo ~/x") == SearchScope("fd", (f"{fake_home}/x",), 2, True)
        assert _scope("find ~ -maxdepth 1 -type d") == SearchScope("find", (str(fake_home),), 1, False)

    def test_unresolved_variable_falls_back_to_cwd(self) -> None:
        scope = _scope("rg foo $UNSET_SEARCH_ROOT_VARIABLE_XYZ")
        assert scope is not None
        assert scope.roots == (CWD,)


class TestEffectiveCwd:
    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            ("cd sub && rg foo", "/w/sub"),
            ("cd /a; cd b && rg x", "/a/b"),
            ("cd - && rg x", CWD),
            ("rg x", CWD),
            ("cd -P sub && rg x", "/w/sub"),
        ],
    )
    def test_replays_preceding_cd(self, command: str, expected: str) -> None:
        commands = extract_commands(bashlex.parse(command))
        assert effective_cwd(commands, len(commands) - 1, CWD) == expected

    @pytest.mark.parametrize("command", ["cd ~ && rg foo", "cd && rg x", "pushd ~ && rg x"])
    def test_home_directory(self, command: str, fake_home: Path) -> None:
        commands = extract_commands(bashlex.parse(command))
        assert effective_cwd(commands, len(commands) - 1, CWD) == str(fake_home)

    def test_ignores_cd_after_the_command(self) -> None:
        commands = extract_commands(bashlex.parse("rg x && cd sub"))
        assert effective_cwd(commands, 0, CWD) == CWD


class TestIsHomeOrAbove:
    def test_filesystem_root(self, fake_home: Path) -> None:
        assert is_home_or_above("/") is True

    def test_home_and_its_ancestors(self, fake_home: Path) -> None:
        assert is_home_or_above(str(fake_home)) is True
        assert is_home_or_above(str(fake_home.parent)) is True

    def test_below_home(self, fake_home: Path) -> None:
        assert is_home_or_above(str(fake_home / "project")) is False

    def test_sibling_sharing_a_name_prefix(self, fake_home: Path) -> None:
        assert is_home_or_above(f"{fake_home}-other") is False

    def test_symlink_to_home(self, fake_home: Path, mocker: MockerFixture) -> None:
        link = "/fake/link"
        resolve = Path.resolve

        def resolve_link(path: Path, strict: bool = False) -> Path:
            return fake_home if str(path) == link else resolve(path, strict=strict)

        mocker.patch.object(Path, "resolve", autospec=True, side_effect=resolve_link)
        assert is_home_or_above(link) is True


@pytest.mark.usefixtures("small_cap", "fake_filesystem")
class TestFindOversizedSearch:
    @pytest.mark.parametrize("command", ["grep -r foo {}", "find {}", "rg foo {}"])
    def test_blocks_a_tree_over_the_entry_cap(self, command: str, fake_filesystem: FakeFilesystem) -> None:
        fake_filesystem.add_files(TREE, BIG)
        assert _oversized(command.format(TREE))

    @pytest.mark.parametrize("command", ["grep -r foo {}", "find {}", "rg foo {}"])
    def test_allows_a_tree_under_the_entry_cap(self, command: str, fake_filesystem: FakeFilesystem) -> None:
        fake_filesystem.add_files(TREE, 3)
        assert _oversized(command.format(TREE)) is None

    def test_counts_entries_across_roots_together(self, fake_filesystem: FakeFilesystem) -> None:
        first = fake_filesystem.add_files("/fake/a", SMALL_CAP // 2 + 1)
        second = fake_filesystem.add_files("/fake/b", SMALL_CAP // 2 + 1)
        assert _oversized(f"rg foo {first} {second}")

    def test_allows_a_missing_path(self) -> None:
        assert _oversized("rg foo /fake/missing") is None

    def test_allows_a_non_search_command(self) -> None:
        assert _oversized("ls -la /") is None

    def test_blocks_the_filesystem_root(self) -> None:
        assert _oversized("find / -name x")

    def test_blocks_home_without_scanning(self, fake_home: Path) -> None:
        assert _oversized("rg foo ~")

    def test_blocks_an_ancestor_of_home(self, fake_home: Path) -> None:
        assert _oversized(f"rg foo {fake_home.parent}")

    def test_blocks_home_reached_through_cd(self, fake_home: Path) -> None:
        assert _oversized("cd ~ && grep -r foo .")

    def test_blocks_a_pathless_search_from_home(self, fake_home: Path) -> None:
        assert _oversized("rg foo", fake_home)

    def test_depth_limit_skips_the_home_check(self, fake_home: Path) -> None:
        assert _oversized("find ~ -maxdepth 1") is None

    def test_zero_depth_is_never_blocked(self, fake_filesystem: FakeFilesystem) -> None:
        fake_filesystem.add_files(TREE, BIG)
        assert _oversized(f"find {TREE} -maxdepth 0") is None

    def test_depth_limit_bounds_the_scan(self, fake_filesystem: FakeFilesystem) -> None:
        for index in range(3):
            fake_filesystem.add_files(fake_filesystem.add_directory(TREE, f"sub{index}"), BIG)
        assert _oversized(f"find {TREE} -maxdepth 1") is None
        assert _oversized(f"find {TREE}")
        assert _oversized(f"rg --max-depth 1 foo {TREE}") is None

    def test_respects_bare_name_gitignore_entries(self, fake_filesystem: FakeFilesystem) -> None:
        fake_filesystem.add_files(TREE, 2)
        fake_filesystem.add_files(fake_filesystem.add_directory(TREE, "node_modules"), BIG)
        fake_filesystem.gitignores[f"{TREE}/.gitignore"] = "node_modules/\n"
        assert _oversized(f"rg foo {TREE}") is None
        assert _oversized(f"grep -r foo {TREE}")
        assert _oversized(f"rg --no-ignore foo {TREE}")

    def test_respecting_tools_skip_hidden_entries(self, fake_filesystem: FakeFilesystem) -> None:
        fake_filesystem.add_files(TREE, 2)
        fake_filesystem.add_files(fake_filesystem.add_directory(TREE, ".venv"), BIG)
        assert _oversized(f"rg foo {TREE}") is None
        assert _oversized(f"rg --hidden foo {TREE}")
        assert _oversized(f"find {TREE}")

    @pytest.mark.parametrize("entry", ["# comment", "!keep", "a/b", "*.log", "file?", "[ab]"])
    def test_gitignore_patterns_beyond_bare_names_are_not_applied(
        self, entry: str, fake_filesystem: FakeFilesystem
    ) -> None:
        fake_filesystem.add_files(TREE, 2)
        fake_filesystem.add_files(fake_filesystem.add_directory(TREE, "big"), BIG)
        fake_filesystem.gitignores[f"{TREE}/.gitignore"] = f"{entry}\n"
        assert _oversized(f"rg foo {TREE}")

    def test_gitignore_entries_may_be_anchored_and_padded(self, fake_filesystem: FakeFilesystem) -> None:
        fake_filesystem.add_files(TREE, 2)
        fake_filesystem.add_files(fake_filesystem.add_directory(TREE, "build"), BIG)
        fake_filesystem.gitignores[f"{TREE}/.gitignore"] = "  /build/  \n"
        assert _oversized(f"rg foo {TREE}") is None

    def test_unreadable_directory_is_skipped(self, fake_filesystem: FakeFilesystem) -> None:
        fake_filesystem.add_files(TREE, 3)
        locked = fake_filesystem.add_files(fake_filesystem.add_directory(TREE, "locked"), BIG)
        fake_filesystem.unreadable.add(locked)
        assert _oversized(f"rg foo {TREE}") is None

    def test_symlinked_directory_is_not_followed(self, fake_filesystem: FakeFilesystem) -> None:
        fake_filesystem.add_files(TREE, 2)
        fake_filesystem.add_files(fake_filesystem.add_directory(TREE, "link", symlink=True), BIG)
        assert _oversized(f"find {TREE}") is None

    def test_slow_walk_counts_as_oversized(self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        release = threading.Event()

        def blocked_listing(path: str) -> Iterator[FakeDirEntry]:
            release.wait(5)
            raise OSError(path)

        mocker.patch("os.scandir", side_effect=blocked_listing)
        monkeypatch.setattr(search_scope_module, "MAX_SCAN_SECONDS", 0.05)
        started = time.monotonic()
        try:
            assert _oversized(f"rg foo {TREE}")
            assert time.monotonic() - started < 1
        finally:
            release.set()
