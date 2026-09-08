from __future__ import annotations

import re
from pathlib import Path

from cline_hooks.core.frontends import FRONTEND_PROTOCOLS
from cline_hooks.core.vocabulary import CanonicalHook

_README_PATH = Path(__file__).parent.parent / "README.md"
_MATRIX_START = "<!-- HOOK_MATRIX_START -->"
_MATRIX_END = "<!-- HOOK_MATRIX_END -->"


def _frontend_display_name(protocol_cls: type) -> str:
    """Derive a frontend's display name from its Protocol class name.

    Returns:
        The class name with the "Protocol" suffix stripped and its
        CamelCase words space-separated (e.g. "ClaudeCodeProtocol" -> "Claude Code").
    """
    return re.sub(
        r"(?<!^)(?=[A-Z])", " ", protocol_cls.__name__.removesuffix("Protocol")
    )


def _generate_hook_matrix() -> str:
    """Build the hook-support matrix table from each frontend's supported_hooks.

    Returns:
        A markdown table with one row per CanonicalHook and one column per
        frontend in FRONTEND_PROTOCOLS, each cell holding the frontend's
        native hook name or "-" if that hook isn't supported.
    """
    headers = [
        _frontend_display_name(protocol_cls) for protocol_cls in FRONTEND_PROTOCOLS
    ]
    lines = [
        "| Canonical hook | " + " | ".join(headers) + " |",
        "|---|" + "---|" * len(headers),
    ]
    for hook in CanonicalHook:
        cells = []
        for protocol_cls in FRONTEND_PROTOCOLS:
            registration = protocol_cls.supported_hooks.get(hook)
            cells.append(
                f"`{registration.native_name}`" if registration is not None else "-"
            )
        lines.append(f"| {hook.value} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


class TestReadmeHookMatrix:
    def test_committed_matrix_matches_supported_hooks(self) -> None:
        readme = _README_PATH.read_text(encoding="utf-8")
        match = re.search(
            rf"{re.escape(_MATRIX_START)}\n(.*?)\n{re.escape(_MATRIX_END)}",
            readme,
            re.DOTALL,
        )
        assert match is not None, "README is missing the hook-matrix markers"
        assert match.group(1) == _generate_hook_matrix()
