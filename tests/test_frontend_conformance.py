from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from cline_hooks.core.frontends import FRONTEND_PROTOCOLS
from cline_hooks.core.models import HookInputPreCompact, PreCompactFields
from cline_hooks.core.payload import StandardPayloadProtocol
from cline_hooks.core.protocol import Protocol, RawPayload
from cline_hooks.core.registry import HOOK_HANDLERS
from cline_hooks.frontends.claude_code.protocol import ClaudeCodeProtocol
from cline_hooks.frontends.cline.protocol import ClineProtocol
from cline_hooks.frontends.codex.protocol import CodexProtocol
from cline_hooks.frontends.copilot.protocol import CopilotProtocol
from cline_hooks.frontends.kiro.protocol import KiroProtocol

FIXTURES_DIR = Path(__file__).parent / "fixtures"

_FIXTURE_NAME: dict[type[Protocol], str] = {
    ClaudeCodeProtocol: "claude_code",
    KiroProtocol: "kiro",
    ClineProtocol: "cline",
}

_DETECT_ENV: dict[type[Protocol], dict[str, str]] = {
    ClaudeCodeProtocol: {"CLAUDECODE": "1"},
    KiroProtocol: {},
    ClineProtocol: {},
}

_OWN_PROTOCOL_MEMBERS = ("detect", "supported_hooks")
_EXCLUDED_PROTOCOLS: tuple[type[Protocol], ...] = (CodexProtocol, CopilotProtocol)


def _fixture_hooks(frontend: str) -> list[str]:
    """Return the canonical hook names with a fixture file for the given frontend.

    Returns:
        Sorted list of canonical hook names (fixture parent directory names).
    """
    return sorted(path.parent.name for path in FIXTURES_DIR.glob(f"*/{frontend}.json"))


def _payload_for(frontend: str, canonical_hook: str) -> RawPayload:
    """Build a RawPayload from a fixture file, using that fixture's own frontend's detect env.

    Returns:
        A RawPayload with `env` set to the env vars that fixture's native frontend relies on.
    """
    raw = (FIXTURES_DIR / canonical_hook / f"{frontend}.json").read_text()
    owner_cls = next(cls for cls, name in _FIXTURE_NAME.items() if name == frontend)
    return RawPayload(raw=raw, data=json.loads(raw), env=_DETECT_ENV[owner_cls])


_ALL_FIXTURE_PAIRS = [
    (frontend, canonical_hook)
    for frontend in _FIXTURE_NAME.values()
    for canonical_hook in _fixture_hooks(frontend)
]


def _concrete_protocols() -> set[type[Protocol]]:
    """Return every concrete Protocol subclass in the package, at any depth.

    Returns:
        The concrete protocol classes, skipping abstract intermediate layers
        such as StandardPayloadProtocol and any synthetic subclass declared
        by a test module (e.g. test doubles built to satisfy a type hint).
    """
    seen: set[type[Protocol]] = set()
    work: list[type[Protocol]] = list(Protocol.__subclasses__())
    while work:
        current = work.pop()
        if current in seen:
            continue
        seen.add(current)
        work.extend(current.__subclasses__())
    return {
        cls
        for cls in seen
        if not inspect.isabstract(cls) and cls.__module__.startswith("cline_hooks.")
    }


@pytest.mark.parametrize(
    "protocol_cls", FRONTEND_PROTOCOLS, ids=lambda cls: cls.__name__
)
class TestFrontendConformance:
    def test_is_concrete_protocol_subclass(self, protocol_cls: type[Protocol]) -> None:
        assert issubclass(protocol_cls, Protocol)
        assert not inspect.isabstract(protocol_cls)

    def test_defines_own_core_members(self, protocol_cls: type[Protocol]) -> None:
        for name in _OWN_PROTOCOL_MEMBERS:
            assert name in protocol_cls.__dict__, (
                f"{protocol_cls.__name__}.{name} is inherited, not overridden"
            )

    def test_supported_hooks_non_empty_and_known(
        self, protocol_cls: type[Protocol]
    ) -> None:
        assert protocol_cls.supported_hooks
        for canonical_hook in protocol_cls.supported_hooks:
            assert canonical_hook in HOOK_HANDLERS

    def test_native_names_unique(self, protocol_cls: type[Protocol]) -> None:
        native_names = [
            registration.native_name
            for registration in protocol_cls.supported_hooks.values()
        ]
        assert len(native_names) == len(set(native_names))

    def test_parses_every_declared_hook_fixture(
        self, protocol_cls: type[Protocol]
    ) -> None:
        frontend = _FIXTURE_NAME[protocol_cls]
        for canonical_hook in protocol_cls.supported_hooks:
            payload = _payload_for(frontend, canonical_hook.value)
            hook = protocol_cls().parse(payload)
            assert hook.hookName == canonical_hook.value

    @pytest.mark.parametrize(("frontend", "canonical_hook"), _ALL_FIXTURE_PAIRS)
    def test_cross_detection_matrix(
        self,
        protocol_cls: type[Protocol],
        frontend: str,
        canonical_hook: str,
    ) -> None:
        payload = _payload_for(frontend, canonical_hook)
        owns_fixture = _FIXTURE_NAME[protocol_cls] == frontend
        assert protocol_cls.detect(payload) is owns_fixture


class TestCopilotDirectParse:
    @pytest.mark.parametrize("canonical_hook", _fixture_hooks("copilot"))
    def test_parses_own_fixture(self, canonical_hook: str) -> None:
        raw = (FIXTURES_DIR / canonical_hook / "copilot.json").read_text()
        payload = RawPayload(raw=raw, data=json.loads(raw), env={})
        hook = CopilotProtocol().parse(payload)
        assert hook.hookName == canonical_hook

    def test_pre_compact_picks_up_shared_session_id_fallback(self) -> None:
        raw = (FIXTURES_DIR / "PreCompact" / "copilot.json").read_text()
        payload = RawPayload(raw=raw, data=json.loads(raw), env={})
        hook = CopilotProtocol().parse(payload)
        assert isinstance(hook, HookInputPreCompact)
        assert isinstance(hook.preCompact, PreCompactFields)
        assert hook.taskId != ""


class TestExcludedProtocols:
    def test_excluded_from_detection_registry(self) -> None:
        for protocol_cls in _EXCLUDED_PROTOCOLS:
            assert protocol_cls not in FRONTEND_PROTOCOLS

    def test_every_concrete_protocol_is_registered_or_excluded(self) -> None:
        assert _concrete_protocols() == set(FRONTEND_PROTOCOLS) | set(
            _EXCLUDED_PROTOCOLS
        )

    def test_standard_payload_protocol_stays_abstract(self) -> None:
        assert inspect.isabstract(StandardPayloadProtocol)

    @pytest.mark.parametrize(("frontend", "canonical_hook"), _ALL_FIXTURE_PAIRS)
    @pytest.mark.parametrize(
        "protocol_cls", _EXCLUDED_PROTOCOLS, ids=lambda cls: cls.__name__
    )
    def test_never_detects_any_fixture(
        self,
        protocol_cls: type[Protocol],
        frontend: str,
        canonical_hook: str,
    ) -> None:
        assert protocol_cls.detect(_payload_for(frontend, canonical_hook)) is False
