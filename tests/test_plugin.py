from __future__ import annotations

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
from cline_hooks.plugins.default import DefaultPlugin


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
        assert plugin.on_hook("AnyHook") is None

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
            def on_hook(self, hook_name: str, **kwargs: object) -> HookResult | None:
                received.update(kwargs)
                return None

        collect_hook_results([PluginA()], "TestHook", task_id="t1", tool_name="test")
        assert received == {"task_id": "t1", "tool_name": "test"}


class TestLoadPlugins:
    def test_returns_list(self) -> None:
        _plugin_cache._loaded = None
        plugins = load_plugins()
        assert isinstance(plugins, list)

    def test_includes_default_plugin(self) -> None:
        _plugin_cache._loaded = None
        plugins = load_plugins()
        assert any(isinstance(p, DefaultPlugin) for p in plugins)

    def test_result_is_cached(self) -> None:
        _plugin_cache._loaded = None
        first = load_plugins()
        second = load_plugins()
        assert first is second

    def test_cache_reset_reloads(self) -> None:
        _plugin_cache._loaded = None
        plugins = load_plugins()
        assert plugins is not None


class TestDefaultPluginBuildCommands:
    def test_contains_just(self) -> None:
        plugin = DefaultPlugin()
        assert "just" in plugin.get_build_commands()

    def test_does_not_contain_brazil_build(self) -> None:
        plugin = DefaultPlugin()
        assert "brazil-build" not in plugin.get_build_commands()

    def test_does_not_contain_eda(self) -> None:
        plugin = DefaultPlugin()
        assert "eda" not in plugin.get_build_commands()

    def test_does_not_contain_bb(self) -> None:
        plugin = DefaultPlugin()
        assert "bb" not in plugin.get_build_commands()


class TestDefaultPluginCommandRules:
    def test_returns_command_rules(self) -> None:
        plugin = DefaultPlugin()
        rules = plugin.get_command_rules()
        assert all(isinstance(r, CommandRule) for r in rules)

    def test_includes_rm_rule(self) -> None:
        plugin = DefaultPlugin()
        commands = [r.command for r in plugin.get_command_rules()]
        assert "rm" in commands

    def test_includes_git_rule(self) -> None:
        plugin = DefaultPlugin()
        commands = [r.command for r in plugin.get_command_rules()]
        assert "git" in commands

    def test_includes_grep_rule(self) -> None:
        plugin = DefaultPlugin()
        commands = [r.command for r in plugin.get_command_rules()]
        assert "grep" in commands


class TestDefaultPluginWorkspaceContext:
    def test_on_hook_returns_none(self) -> None:
        plugin = DefaultPlugin()
        assert plugin.on_hook("TaskStart", workspace_roots=[]) is None


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
