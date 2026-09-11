from __future__ import annotations

from typing import NoReturn

import pytest

from cline_hooks.core.frontend import (
    EXACT_MATCH,
    REGISTERED_FRONTENDS,
    SHAPE_SNIFF,
    FrontendSpec,
    frontend,
)
from cline_hooks.core.frontends import FRONTENDS, FRONTENDS_BY_NAME
from cline_hooks.core.protocol import Protocol, RawPayload
from cline_hooks.core.transcript import NULL_TRANSCRIPT, NullTranscriptReader
from cline_hooks.core.vocabulary import CanonicalTool


class _Bare(Protocol):
    """A protocol declaring nothing beyond what Protocol requires."""

    @classmethod
    def detect(cls, payload: RawPayload) -> bool:
        return False

    def parse(self, payload: RawPayload) -> NoReturn:
        raise NotImplementedError

    def allow(
        self, message: str | None = None, *, system_message: str | None = None
    ) -> NoReturn:
        raise NotImplementedError

    def block(self, message: str) -> NoReturn:
        raise NotImplementedError


class TestFrontendDecorator:
    def test_registers_the_decorated_protocol(self) -> None:
        before = dict(REGISTERED_FRONTENDS)
        try:

            @frontend(name="test-only", display_name="Test Only")
            class _Registered(_Bare):
                pass

            spec = REGISTERED_FRONTENDS["test-only"]
            assert spec.protocol is _Registered
            assert spec.display_name == "Test Only"
            assert spec.detect_priority == SHAPE_SNIFF
            assert spec.default is False
        finally:
            REGISTERED_FRONTENDS.clear()
            REGISTERED_FRONTENDS.update(before)

    def test_the_spec_is_reachable_from_the_protocol(self) -> None:
        before = dict(REGISTERED_FRONTENDS)
        try:

            @frontend(
                name="test-only", display_name="Test Only", detect_priority=EXACT_MATCH
            )
            class _Registered(_Bare):
                pass

            assert _Registered.frontend_spec is REGISTERED_FRONTENDS["test-only"]
            assert _Registered.frontend_spec is not None
            assert _Registered.frontend_spec.detect_priority == EXACT_MATCH
        finally:
            REGISTERED_FRONTENDS.clear()
            REGISTERED_FRONTENDS.update(before)

    def test_a_duplicate_name_is_refused(self) -> None:
        before = dict(REGISTERED_FRONTENDS)
        try:

            @frontend(name="test-only", display_name="First")
            class _First(_Bare):
                pass

            with pytest.raises(RuntimeError, match="already registered by _First"):

                @frontend(name="test-only", display_name="Second")
                class _Second(_Bare):
                    pass
        finally:
            REGISTERED_FRONTENDS.clear()
            REGISTERED_FRONTENDS.update(before)

    def test_re_decorating_the_same_class_is_allowed(self) -> None:
        before = dict(REGISTERED_FRONTENDS)
        try:

            class _Registered(_Bare):
                pass

            decorate = frontend(name="test-only", display_name="Test Only")
            assert decorate(_Registered) is _Registered
            assert decorate(_Registered) is _Registered
        finally:
            REGISTERED_FRONTENDS.clear()
            REGISTERED_FRONTENDS.update(before)


class TestProtocolDefaults:
    def test_a_frontend_has_no_transcript_unless_it_declares_one(self) -> None:
        assert _Bare.transcript is NULL_TRANSCRIPT
        assert isinstance(_Bare.transcript, NullTranscriptReader)
        assert _Bare.transcript.context_tokens("/some/path") is None
        assert _Bare.transcript.turn_assistant_text("/some/path") == ""

    def test_an_undeclared_frontend_carries_no_spec(self) -> None:
        assert _Bare.frontend_spec is None


class TestNativeToolName:
    def test_falls_back_to_the_canonical_name(self) -> None:
        assert _Bare.native_tool_name(CanonicalTool.SPAWN_AGENT) == "spawn_agent"

    def test_uses_the_frontends_own_name_where_it_has_one(self) -> None:
        claude_code = FRONTENDS_BY_NAME["claude-code"].protocol
        cline = FRONTENDS_BY_NAME["cline"].protocol
        assert claude_code.native_tool_name(CanonicalTool.SPAWN_AGENT) == "Task"
        assert cline.native_tool_name(CanonicalTool.SPAWN_AGENT) == "new_task"
        assert claude_code.native_tool_name(CanonicalTool.SHELL) == "Bash"

    def test_canonical_name_stands_in_for_a_tool_the_frontend_never_renames(
        self,
    ) -> None:
        kiro = FRONTENDS_BY_NAME["kiro"].protocol
        assert kiro.native_tool_name(CanonicalTool.SPAWN_AGENT) == "spawn_agent"


class TestFires:
    def test_true_for_a_hook_the_frontend_declares(self) -> None:
        for spec in FRONTENDS:
            for canonical_hook in spec.protocol.supported_hooks:
                assert spec.protocol.fires(canonical_hook.value)

    def test_false_for_a_hook_the_frontend_does_not_declare(self) -> None:
        assert FRONTENDS_BY_NAME["claude-code"].protocol.fires("PreCompact") is False
        assert FRONTENDS_BY_NAME["kiro"].protocol.fires("TaskResume") is False

    def test_false_for_an_unknown_event_name(self) -> None:
        for spec in FRONTENDS:
            assert spec.protocol.fires("NotAHook") is False


class TestFrontendSpecInstall:
    def test_delegates_to_the_installer_with_its_protocol(self) -> None:
        calls: list[tuple[type[Protocol], str | None]] = []

        class _Recorder:
            help = "test"
            argument = None

            def install(self, protocol_cls: type[Protocol], target: str | None) -> None:
                calls.append((protocol_cls, target))

        spec = FrontendSpec(
            name="test-only",
            display_name="Test Only",
            protocol=_Bare,
            installer=_Recorder(),  # type: ignore[arg-type]
        )
        spec.install("/somewhere")
        assert calls == [(_Bare, "/somewhere")]
