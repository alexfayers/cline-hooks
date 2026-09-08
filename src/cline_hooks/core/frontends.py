"""Registry of known frontend protocols and detection dispatch."""

from __future__ import annotations

from cline_hooks.core.protocol import Protocol, RawPayload
from cline_hooks.frontends.claude_code.protocol import ClaudeCodeProtocol
from cline_hooks.frontends.cline.protocol import ClineProtocol
from cline_hooks.frontends.kiro.protocol import KiroProtocol

# CodexProtocol and CopilotProtocol are excluded deliberately: both reuse Claude Code's
# payload shape, and neither frontend exposes an env or payload signal distinguishing it
# from a real Claude Code invocation, so ClaudeCodeProtocol's detect claims their payloads
# and parses them correctly. tests/test_frontend_conformance.py asserts this exclusion set.
FRONTEND_PROTOCOLS: tuple[type[Protocol], ...] = (
    ClaudeCodeProtocol,
    KiroProtocol,
    ClineProtocol,
)
DEFAULT_PROTOCOL: type[Protocol] = ClineProtocol


def select_protocol(payload: RawPayload) -> type[Protocol]:
    """Return the frontend protocol class that detects this payload, or the default."""
    for proto in FRONTEND_PROTOCOLS:
        if proto.detect(payload):
            return proto
    return DEFAULT_PROTOCOL
