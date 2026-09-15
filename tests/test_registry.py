from __future__ import annotations

from typing import cast

import pytest

import cline_hooks.handlers  # noqa: F401
from cline_hooks.core.outcome import Outcome
from cline_hooks.core.registry import (
    HOOK_HANDLERS,
    TOOL_HANDLERS,
    hook_handler,
    tool_handler,
)
from cline_hooks.core.vocabulary import CanonicalHook, CanonicalTool


class TestHookHandler:
    def test_registers_handler(self) -> None:
        test_hook = cast("CanonicalHook", "TestHookXYZ")

        @hook_handler(test_hook)
        def my_handler() -> None:
            pass

        assert HOOK_HANDLERS[test_hook] is my_handler

    def test_returns_original_function(self) -> None:
        def my_handler() -> None:
            pass

        result = hook_handler(cast("CanonicalHook", "TestHookABC"))(my_handler)
        assert result is my_handler

    def test_overwrites_existing_registration(self) -> None:
        test_hook = cast("CanonicalHook", "TestHookDEF")

        @hook_handler(test_hook)
        def first() -> None:
            pass

        @hook_handler(test_hook)
        def second() -> None:
            pass

        assert HOOK_HANDLERS[test_hook] is second


class TestToolHandler:
    _EXPECTED_KEYS = [
        (CanonicalHook.PRE_TOOL_USE, CanonicalTool.PLAN_MODE_RESPOND),
        (CanonicalHook.PRE_TOOL_USE, CanonicalTool.READ),
        (CanonicalHook.PRE_TOOL_USE, CanonicalTool.SHELL),
        (CanonicalHook.PRE_TOOL_USE, CanonicalTool.EDIT),
        (CanonicalHook.PRE_TOOL_USE, CanonicalTool.WRITE),
        (CanonicalHook.PRE_TOOL_USE, CanonicalTool.MCP),
        (CanonicalHook.PRE_TOOL_USE, CanonicalTool.ATTEMPT_COMPLETION),
        (CanonicalHook.POST_TOOL_USE, CanonicalTool.EDIT),
        (CanonicalHook.POST_TOOL_USE, CanonicalTool.WRITE),
        (CanonicalHook.POST_TOOL_USE, CanonicalTool.SHELL),
    ]

    @pytest.mark.parametrize("key", _EXPECTED_KEYS)
    def test_expected_key_is_registered(
        self, key: tuple[CanonicalHook, CanonicalTool]
    ) -> None:
        assert key in TOOL_HANDLERS

    def test_decorator_registers_same_function_under_every_tool(self) -> None:
        test_hook = cast("CanonicalHook", "TestHookGHI")
        tool_a = cast("CanonicalTool", "test-tool-a")
        tool_b = cast("CanonicalTool", "test-tool-b")
        try:

            @tool_handler(test_hook, tool_a, tool_b)
            def handler(*_args: object) -> Outcome:
                return Outcome()

            assert TOOL_HANDLERS[test_hook, tool_a] is handler
            assert TOOL_HANDLERS[test_hook, tool_b] is handler
        finally:
            TOOL_HANDLERS.pop((test_hook, tool_a), None)
            TOOL_HANDLERS.pop((test_hook, tool_b), None)

    def test_unregistered_pair_returns_none(self) -> None:
        test_hook = cast("CanonicalHook", "TestHookJKL")
        test_tool = cast("CanonicalTool", "no-such-tool")
        assert TOOL_HANDLERS.get((test_hook, test_tool)) is None
