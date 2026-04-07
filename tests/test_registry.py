from __future__ import annotations

from cline_hooks.core.registry import HOOK_HANDLERS, hook_handler


class TestHookHandler:
    def test_registers_handler(self) -> None:
        @hook_handler("TestHookXYZ")
        def my_handler() -> None:
            pass

        assert HOOK_HANDLERS["TestHookXYZ"] is my_handler

    def test_returns_original_function(self) -> None:
        def my_handler() -> None:
            pass

        result = hook_handler("TestHookABC")(my_handler)
        assert result is my_handler

    def test_overwrites_existing_registration(self) -> None:
        @hook_handler("TestHookDEF")
        def first() -> None:
            pass

        @hook_handler("TestHookDEF")
        def second() -> None:
            pass

        assert HOOK_HANDLERS["TestHookDEF"] is second
