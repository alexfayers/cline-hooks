from __future__ import annotations

from cline_hooks.core.plugin import HooksPlugin, collect_contributions, hookimpl, plugins_override
from tests.conftest import GreeterOwner, GreeterSpec


def greeter(result: object) -> HooksPlugin:
    class Greeter(HooksPlugin):
        @hookimpl
        def greetings(self, name: str) -> object:
            if isinstance(result, Exception):
                raise result
            return result

    return Greeter()


def collect_greetings(plugins: list[HooksPlugin]) -> list[list[str]]:
    with plugins_override(plugins):
        return collect_contributions(GreeterSpec.greetings, list, name="Ada")


class TestCollectContributions:
    def test_a_raising_contribution_leaves_the_other_contributions(self) -> None:
        plugins = [GreeterOwner(), greeter(RuntimeError("boom")), greeter(["hello Ada"])]

        assert collect_greetings(plugins) == [["hello Ada"]]

    def test_a_wrong_typed_contribution_is_left_out(self) -> None:
        plugins = [GreeterOwner(), greeter("hello Ada"), greeter(["hello Ada"])]

        assert collect_greetings(plugins) == [["hello Ada"]]

    def test_a_none_contribution_is_left_out(self) -> None:
        plugins = [GreeterOwner(), greeter(None), greeter(["hello Ada"])]

        assert collect_greetings(plugins) == [["hello Ada"]]

    def test_a_later_loaded_contribution_comes_before_an_earlier_one(self) -> None:
        plugins = [GreeterOwner(), greeter(["bundled"]), greeter(["external"])]

        assert collect_greetings(plugins) == [["external"], ["bundled"]]
