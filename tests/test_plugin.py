from __future__ import annotations

import importlib
import importlib.metadata
import logging
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

from cline_hooks.core.plugin import (
    HookResult,
    HooksPlugin,
    ToolingNote,
    UserFacingNote,
    _plugin_cache,
    collect_hook_results,
    load_plugins,
)
from cline_hooks.handlers.commands import (
    CommandRule,
    get_all_build_commands,
    get_all_command_rules,
)
import cline_hooks.plugins as plugins_pkg
from cline_hooks.plugins.command_rules import CommandRulesPlugin


class TestHooksPluginDefaults:
    def test_get_build_commands_returns_empty(self) -> None:
        plugin = HooksPlugin()
        assert plugin.get_build_commands() == frozenset()

    def test_get_command_rules_returns_empty(self) -> None:
        plugin = HooksPlugin()
        assert plugin.get_command_rules() == []

    def test_get_state_write_tool_names_returns_empty(self) -> None:
        plugin = HooksPlugin()
        assert plugin.get_state_write_tool_names() == frozenset()

    def test_get_research_detail_extractors_returns_empty(self) -> None:
        plugin = HooksPlugin()
        assert plugin.get_research_detail_extractors() == {}

    def test_on_hook_returns_none(self) -> None:
        plugin = HooksPlugin()
        assert plugin.on_hook("AnyHook", logger=logging.getLogger("test")) is None

    def test_get_tooling_note_returns_none(self) -> None:
        plugin = HooksPlugin()
        assert plugin.get_tooling_note([]) is None


class TestHookResult:
    def test_defaults(self) -> None:
        result = HookResult()
        assert result.notes == []
        assert result.block is None

    def test_with_values(self) -> None:
        result = HookResult(notes=["note1"], block="blocked")
        assert result.notes == ["note1"]
        assert result.block == "blocked"

    def test_user_notes_defaults_empty(self) -> None:
        result = HookResult()
        assert result.user_notes == []


class TestToolingNote:
    def test_defaults(self) -> None:
        note = ToolingNote(note="hello")
        assert note.note == "hello"
        assert note.replaces_generic is True

    def test_with_values(self) -> None:
        note = ToolingNote(note="hello", replaces_generic=False)
        assert note.note == "hello"
        assert note.replaces_generic is False


class TestCollectHookResults:
    def test_no_plugins_returns_empty(self) -> None:
        result = collect_hook_results([], "TestHook")
        assert result.notes == []
        assert result.block is None

    def test_merges_notes(self) -> None:
        class PluginA(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
                return HookResult(notes=["a"])

        class PluginB(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
                return HookResult(notes=["b"])

        result = collect_hook_results([PluginA(), PluginB()], "TestHook")
        assert result.notes == ["a", "b"]
        assert result.block is None

    def test_merges_user_notes(self) -> None:
        class PluginA(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
                return HookResult(user_notes=[UserFacingNote(user_text="ua")])

        class PluginB(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
                return HookResult(user_notes=[UserFacingNote(user_text="ub")])

        result = collect_hook_results([PluginA(), PluginB()], "TestHook")
        assert [n.user_text for n in result.user_notes] == ["ua", "ub"]

    def test_first_block_wins(self) -> None:
        class PluginA(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
                return HookResult(block="block-a")

        class PluginB(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
                return HookResult(block="block-b")

        result = collect_hook_results([PluginA(), PluginB()], "TestHook")
        assert result.block == "block-a"

    def test_none_results_skipped(self) -> None:
        class PluginA(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
                return None

        class PluginB(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
                return HookResult(notes=["b"])

        result = collect_hook_results([PluginA(), PluginB()], "TestHook")
        assert result.notes == ["b"]

    def test_kwargs_passed_through(self) -> None:
        received: dict[str, object] = {}

        class PluginA(HooksPlugin):
            def on_hook(self, hook_name: str, *, logger: logging.Logger, **kwargs: object) -> HookResult | None:
                received.update(kwargs)
                return None

        collect_hook_results([PluginA()], "TestHook", task_id="t1", tool_name="test")
        assert received == {"task_id": "t1", "tool_name": "test"}

    def test_skips_blank_and_whitespace_only_notes(self) -> None:
        class PluginA(HooksPlugin):
            def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
                return HookResult(notes=["", "  ", "real"])

        result = collect_hook_results([PluginA()], "TestHook")
        assert result.notes == ["real"]


class TestLoadPlugins:
    @pytest.fixture(autouse=True)
    def _reset_plugin_cache(self) -> Iterator[None]:
        _plugin_cache._loaded = None
        yield
        _plugin_cache._loaded = None

    def test_returns_list(self) -> None:
        _plugin_cache._loaded = None
        plugins = load_plugins()
        assert isinstance(plugins, list)

    def test_includes_command_rules_plugin(self) -> None:
        _plugin_cache._loaded = None
        plugins = load_plugins()
        assert any(isinstance(p, CommandRulesPlugin) for p in plugins)

    def test_result_is_cached(self) -> None:
        _plugin_cache._loaded = None
        first = load_plugins()
        second = load_plugins()
        assert first is second

    def test_cache_reset_reloads(self) -> None:
        _plugin_cache._loaded = None
        plugins = load_plugins()
        assert plugins is not None

    def test_subclass_visible_in_two_bundled_modules_loaded_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        origin_name = "cline_hooks.plugins.temp_origin_plugin"
        reexport_name = "cline_hooks.plugins.temp_reexport_plugin"
        (tmp_path / "temp_origin_plugin.py").write_text(
            "from cline_hooks.core.plugin import HooksPlugin\n\n\nclass FakePlugin(HooksPlugin):\n    pass\n"
        )
        (tmp_path / "temp_reexport_plugin.py").write_text(
            'from cline_hooks.plugins.temp_origin_plugin import FakePlugin\n\n__all__ = ["FakePlugin"]\n'
        )

        def fake_entry_points(
            **_kwargs: object,
        ) -> tuple[importlib.metadata.EntryPoint, ...]:
            return ()

        monkeypatch.setattr(plugins_pkg, "__path__", [*plugins_pkg.__path__, str(tmp_path)])
        monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points)

        try:
            plugins = load_plugins()
            origin_module = importlib.import_module(origin_name)
            assert sum(isinstance(p, origin_module.FakePlugin) for p in plugins) == 1
        finally:
            sys.modules.pop(origin_name, None)
            sys.modules.pop(reexport_name, None)


class TestGetAllBuildCommands:
    def test_empty_plugins_returns_empty(self) -> None:
        assert get_all_build_commands([]) == frozenset()

    def test_aggregates_from_multiple_plugins(self) -> None:
        class PluginA(HooksPlugin):
            def get_build_commands(self) -> frozenset[str]:
                return frozenset({"make"})

        class PluginB(HooksPlugin):
            def get_build_commands(self) -> frozenset[str]:
                return frozenset({"gradle"})

        result = get_all_build_commands([PluginA(), PluginB()])
        assert result == frozenset({"make", "gradle"})

    def test_deduplicates_commands(self) -> None:
        class PluginA(HooksPlugin):
            def get_build_commands(self) -> frozenset[str]:
                return frozenset({"make"})

        class PluginB(HooksPlugin):
            def get_build_commands(self) -> frozenset[str]:
                return frozenset({"make"})

        result = get_all_build_commands([PluginA(), PluginB()])
        assert result == frozenset({"make"})


class TestGetAllCommandRules:
    def test_empty_plugins_returns_empty(self) -> None:
        assert get_all_command_rules([]) == []

    def test_aggregates_rules_in_order(self) -> None:
        rule_a = CommandRule(command="foo", message="foo blocked")
        rule_b = CommandRule(command="bar", message="bar blocked")

        class PluginA(HooksPlugin):
            def get_command_rules(self) -> list[CommandRule]:
                return [rule_a]

        class PluginB(HooksPlugin):
            def get_command_rules(self) -> list[CommandRule]:
                return [rule_b]

        result = get_all_command_rules([PluginA(), PluginB()])
        assert result == [rule_a, rule_b]
