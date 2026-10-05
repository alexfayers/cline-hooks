from __future__ import annotations

from collections.abc import Callable
import importlib.metadata
import sys
from types import ModuleType
from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.plugin import HooksPlugin, _entry_point_plugins, get_plugin_problems, load_plugins
from tests.conftest import FAKE_PLUGIN_PREFIX

if TYPE_CHECKING:
    from pathlib import Path

ENTRY_POINT_GROUP = "cline_hooks"

pytestmark = pytest.mark.usefixtures("fresh_plugin_cache")

WriteModule = Callable[[str, str], None]
RegisterModule = Callable[..., ModuleType]
LoadWithEntryPoints = Callable[..., list[HooksPlugin]]


def plugin_source(*class_names: str) -> str:
    classes = "\n\n".join(f"class {name}(HooksPlugin):\n    pass\n" for name in class_names)
    return f"from cline_hooks.core.plugin import HooksPlugin\n\n\n{classes}"


def external_names(plugins: list[HooksPlugin]) -> list[str]:
    return [type(p).__name__ for p in plugins if type(p).__module__.startswith(FAKE_PLUGIN_PREFIX)]


def plugin_class(name: str, module: str) -> type[HooksPlugin]:
    return type(name, (HooksPlugin,), {"__module__": module})


@pytest.fixture
def register_module(monkeypatch: pytest.MonkeyPatch) -> RegisterModule:
    def _register(name: str, *attributes: type) -> ModuleType:
        module = ModuleType(name)
        for attribute in attributes:
            setattr(module, attribute.__name__, attribute)
        monkeypatch.setitem(sys.modules, name, module)
        return module

    return _register


@pytest.fixture
def write_module(tmp_path: Path) -> WriteModule:
    def _write(dotted_name: str, source: str) -> None:
        path = tmp_path.joinpath(*dotted_name.split(".")).with_suffix(".py")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)

    return _write


@pytest.fixture
def load_with_entry_points(monkeypatch: pytest.MonkeyPatch) -> LoadWithEntryPoints:
    def _load(*specs: tuple[str, str]) -> list[HooksPlugin]:
        entry_points = tuple(importlib.metadata.EntryPoint(name, value, ENTRY_POINT_GROUP) for name, value in specs)
        monkeypatch.setattr(importlib.metadata, "entry_points", lambda **_kwargs: entry_points)
        return load_plugins()

    return _load


class TestEntryPointLoading:
    def test_module_entry_point_yields_only_classes_defined_in_it(
        self, register_module: RegisterModule, load_with_entry_points: LoadWithEntryPoints
    ) -> None:
        register_module(
            "fakeep_module",
            plugin_class("ImportedPlugin", "fakeep_elsewhere"),
            plugin_class("FirstPlugin", "fakeep_module"),
            plugin_class("SecondPlugin", "fakeep_module"),
        )

        plugins = load_with_entry_points(("module", "fakeep_module"))

        assert sorted(external_names(plugins)) == ["FirstPlugin", "SecondPlugin"]

    def test_entry_points_load_in_name_order(
        self, register_module: RegisterModule, load_with_entry_points: LoadWithEntryPoints
    ) -> None:
        register_module("fakeep_a", plugin_class("APlugin", "fakeep_a"))
        register_module("fakeep_b", plugin_class("BPlugin", "fakeep_b"))

        plugins = load_with_entry_points(("b", "fakeep_b:BPlugin"), ("a", "fakeep_a:APlugin"))

        assert external_names(plugins) == ["APlugin", "BPlugin"]

    def test_entry_point_naming_a_non_plugin_provides_nothing(self) -> None:
        assert _entry_point_plugins(dict) == []
        assert _entry_point_plugins("text") == []

    def test_package_entry_point_loads_submodules_alphabetically(
        self, write_module: WriteModule, load_with_entry_points: LoadWithEntryPoints
    ) -> None:
        write_module("fakeep_pkg.__init__", "")
        write_module("fakeep_pkg.zeta", plugin_source("ZetaPlugin"))
        write_module("fakeep_pkg.alpha", plugin_source("AlphaPlugin"))
        write_module("fakeep_pkg.mid", plugin_source("MidPlugin"))

        plugins = load_with_entry_points(("pkg", "fakeep_pkg"))

        assert external_names(plugins) == ["AlphaPlugin", "MidPlugin", "ZetaPlugin"]

    def test_package_submodule_import_failure_leaves_other_submodules_loaded(
        self, write_module: WriteModule, load_with_entry_points: LoadWithEntryPoints
    ) -> None:
        write_module("fakeep_pkg.__init__", "")
        write_module("fakeep_pkg.alpha", plugin_source("AlphaPlugin"))
        write_module("fakeep_pkg.broken", "raise RuntimeError('boom')\n")
        write_module("fakeep_pkg.zeta", plugin_source("ZetaPlugin"))

        plugins = load_with_entry_points(("pkg", "fakeep_pkg"))

        assert external_names(plugins) == ["AlphaPlugin", "ZetaPlugin"]


class TestPluginProblems:
    def test_plugin_defining_a_removed_method_is_reported(
        self, register_module: RegisterModule, load_with_entry_points: LoadWithEntryPoints
    ) -> None:
        legacy = type(
            "LegacyPlugin",
            (HooksPlugin,),
            {"__module__": "fakeep_legacy", "get_build_commands": lambda _: frozenset()},
        )
        register_module("fakeep_legacy", legacy)

        load_with_entry_points(("legacy", "fakeep_legacy:LegacyPlugin"))

        assert get_plugin_problems() == ["LegacyPlugin defines removed method get_build_commands, which is ignored"]

    def test_entry_point_that_fails_to_import_is_reported(self, load_with_entry_points: LoadWithEntryPoints) -> None:
        load_with_entry_points(("missing", "fakeep_missing:MissingPlugin"))

        assert get_plugin_problems() == ["External plugin missing failed to load and is ignored"]
