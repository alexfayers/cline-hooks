from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from cline_hooks.core.frontend import FrontendSpec
from cline_hooks.core.frontends import (
    DETECTION_ORDER,
    FRONTENDS,
    FRONTENDS_BY_NAME,
    select_protocol,
)
from cline_hooks.core.install import Installer
from cline_hooks.core.payload import StandardPayloadProtocol
from cline_hooks.core.protocol import Protocol, RawPayload
from cline_hooks.core.registry import HOOK_HANDLERS

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Env a frontend's own hook invocation carries, where its detection reads one.
_DETECT_ENV: dict[str, dict[str, str]] = {"claude-code": {"CLAUDECODE": "1"}}

# A frontend whose payloads are shaped exactly like another frontend's, and so
# cannot be told apart from it by shape alone.
_SHAPE_SOURCE: dict[str, str] = {"codex": "claude-code", "copilot": "claude-code"}

# Which frontend should end up handling each frontend's payloads. A frontend
# that borrows another's shape is handled by the frontend it borrows from,
# which parses it identically - except where it fires an event the shape
# source has no counterpart for, which only it can have sent.
_ROUTE_EXCEPTIONS: dict[tuple[str, str], str] = {("copilot", "PreCompact"): "copilot"}


def _fixture_hooks(name: str) -> list[str]:
    """Return the canonical hook names with a fixture file for the given frontend.

    Returns:
        Sorted list of canonical hook names (fixture parent directory names).
    """
    return sorted(path.parent.name for path in FIXTURES_DIR.glob(f"*/{name}.json"))


def _fixture_owner(spec: FrontendSpec) -> str:
    """Return the frontend whose fixtures exercise this one.

    Returns:
        The frontend's own name, or - where it has no fixtures of its own -
        the name of the frontend whose payload shape it reuses wholesale.
    """
    if _fixture_hooks(spec.name):
        return spec.name
    return _SHAPE_SOURCE.get(spec.name, spec.name)


def _expected_route(name: str, canonical_hook: str) -> str:
    """Return the frontend that should handle one fixture's payload.

    Returns:
        The name of the frontend `select_protocol` is expected to pick.
    """
    exception = _ROUTE_EXCEPTIONS.get((name, canonical_hook))
    if exception is not None:
        return exception
    return _SHAPE_SOURCE.get(name, name)


def _payload_for(name: str, canonical_hook: str) -> RawPayload:
    """Build a RawPayload from a fixture, with the env that fixture's frontend carries.

    Returns:
        A RawPayload as the owning frontend would deliver it.
    """
    raw = (FIXTURES_DIR / canonical_hook / f"{name}.json").read_text()
    return RawPayload(raw=raw, data=json.loads(raw), env=_DETECT_ENV.get(name, {}))


_FIXTURE_FRONTENDS = [
    spec for spec in FRONTENDS if _fixture_hooks(_fixture_owner(spec))
]
_ALL_FIXTURE_PAIRS = [
    (name, canonical_hook)
    for name in sorted({_fixture_owner(spec) for spec in FRONTENDS})
    for canonical_hook in _fixture_hooks(name)
]

# Every (frontend, foreign fixture) pair whose payload shapes genuinely differ,
# so one must never claim the other's payload.
_FOREIGN_SHAPE_PAIRS = [
    (spec, name, canonical_hook)
    for spec in FRONTENDS
    for name, canonical_hook in _ALL_FIXTURE_PAIRS
    if _SHAPE_SOURCE.get(name, name) != _SHAPE_SOURCE.get(spec.name, spec.name)
]


def _concrete_protocols() -> set[type[Protocol]]:
    """Return every concrete Protocol subclass in the package, at any depth.

    Returns:
        The concrete protocol classes, skipping abstract layers such as
        StandardPayloadProtocol or a frontend's payload spec, and any
        synthetic subclass declared by a test module.
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


@pytest.mark.parametrize("spec", FRONTENDS, ids=lambda spec: spec.name)
class TestFrontendConformance:
    """Every registered frontend, whatever it is, must satisfy these."""

    def test_protocol_is_concrete(self, spec: FrontendSpec) -> None:
        assert issubclass(spec.protocol, Protocol)
        assert not inspect.isabstract(spec.protocol)

    def test_declares_its_own_detection(self, spec: FrontendSpec) -> None:
        assert "detect" in spec.protocol.__dict__, (
            f"{spec.protocol.__name__}.detect is inherited, not declared"
        )

    def test_supported_hooks_are_non_empty_and_handled(
        self, spec: FrontendSpec
    ) -> None:
        assert spec.protocol.supported_hooks
        for canonical_hook in spec.protocol.supported_hooks:
            assert canonical_hook in HOOK_HANDLERS

    def test_native_hook_names_are_unique(self, spec: FrontendSpec) -> None:
        native_names = [
            registration.native_name
            for registration in spec.protocol.supported_hooks.values()
        ]
        assert len(native_names) == len(set(native_names))

    def test_spec_is_reachable_from_its_protocol(self, spec: FrontendSpec) -> None:
        assert spec.protocol.frontend_spec is spec

    def test_installer_is_an_installer(self, spec: FrontendSpec) -> None:
        assert isinstance(spec.installer, Installer)


@pytest.mark.parametrize("spec", _FIXTURE_FRONTENDS, ids=lambda spec: spec.name)
class TestFrontendParsing:
    def test_parses_every_hook_it_registers(self, spec: FrontendSpec) -> None:
        owner = _fixture_owner(spec)
        available = set(_fixture_hooks(owner))
        for canonical_hook in spec.protocol.supported_hooks:
            if canonical_hook.value not in available:
                continue
            hook = spec.protocol().parse(_payload_for(owner, canonical_hook.value))
            assert hook.hookName == canonical_hook.value


@pytest.mark.parametrize(
    ("spec", "name", "canonical_hook"),
    _FOREIGN_SHAPE_PAIRS,
    ids=lambda value: value.name if isinstance(value, FrontendSpec) else str(value),
)
def test_a_frontend_never_detects_a_differently_shaped_payload(
    spec: FrontendSpec, name: str, canonical_hook: str
) -> None:
    assert spec.protocol.detect(_payload_for(name, canonical_hook)) is False


class TestBorrowedShapeFrontends:
    """Frontends whose payloads are shaped exactly like another frontend's.

    They cannot claim an ordinary payload, so detection falls through to the
    frontend they borrow their shape from - which by construction parses it
    the same way. Installing them still matters: that is how their hooks get
    wired up, and an event their shape source never fires is theirs to claim.
    """

    @pytest.mark.parametrize(("name", "canonical_hook"), _ALL_FIXTURE_PAIRS)
    def test_every_payload_routes_to_the_frontend_that_should_handle_it(
        self, name: str, canonical_hook: str
    ) -> None:
        payload = _payload_for(name, canonical_hook)
        expected = FRONTENDS_BY_NAME[_expected_route(name, canonical_hook)]
        assert select_protocol(payload) is expected.protocol

    @pytest.mark.parametrize("name", sorted(_SHAPE_SOURCE))
    def test_borrowed_payloads_parse_identically_at_their_shape_source(
        self, name: str
    ) -> None:
        spec = FRONTENDS_BY_NAME[name]
        source = FRONTENDS_BY_NAME[_SHAPE_SOURCE[name]]
        for canonical_hook in _fixture_hooks(_fixture_owner(spec)):
            if _ROUTE_EXCEPTIONS.get((name, canonical_hook)):
                continue
            payload = _payload_for(_fixture_owner(spec), canonical_hook)
            assert (
                source.protocol().parse(payload).model_dump()
                == spec.protocol().parse(payload).model_dump()
            )

    def test_an_own_event_carries_fields_its_shape_source_would_drop(self) -> None:
        payload = _payload_for("copilot", "PreCompact")
        copilot = FRONTENDS_BY_NAME["copilot"].protocol
        claude_code = FRONTENDS_BY_NAME["claude-code"].protocol
        assert copilot().parse(payload).model_dump()["preCompact"] == {
            "conversationLength": 10,
            "estimatedTokens": 1000,
        }
        assert "preCompact" not in claude_code().parse(payload).model_dump()


class TestRegistry:
    def test_every_concrete_protocol_is_a_registered_frontend(self) -> None:
        assert _concrete_protocols() == {spec.protocol for spec in FRONTENDS}

    def test_frontend_names_are_unique(self) -> None:
        names = [spec.name for spec in FRONTENDS]
        assert len(names) == len(set(names))

    def test_exactly_one_default_frontend(self) -> None:
        assert len([spec for spec in FRONTENDS if spec.default]) == 1

    def test_shape_sniffing_runs_after_exact_matches(self) -> None:
        priorities = [spec.detect_priority for spec in DETECTION_ORDER]
        assert priorities == sorted(priorities, reverse=True)

    def test_standard_payload_protocol_stays_abstract(self) -> None:
        assert inspect.isabstract(StandardPayloadProtocol)

    def test_unknown_payload_falls_back_to_the_default_frontend(self) -> None:
        payload = RawPayload(raw="{}", data={}, env={})
        default = next(spec for spec in FRONTENDS if spec.default)
        assert select_protocol(payload) is default.protocol
