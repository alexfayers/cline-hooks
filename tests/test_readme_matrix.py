from __future__ import annotations

from pathlib import Path
import re

from cline_hooks.core.frontends import FRONTENDS
from cline_hooks.core.plugin import _package_plugins, list_extension_points
from cline_hooks.core.vocabulary import CanonicalHook
import cline_hooks.plugins

_README_PATH = Path(__file__).parent.parent / "README.md"
_MATRIX_START = "<!-- HOOK_MATRIX_START -->"
_MATRIX_END = "<!-- HOOK_MATRIX_END -->"
_EXTENSION_POINTS_START = "<!-- EXTENSION_POINTS_START -->"
_EXTENSION_POINTS_END = "<!-- EXTENSION_POINTS_END -->"


def _generate_hook_matrix() -> str:
    """Build the hook-support matrix table from each frontend's supported_hooks.

    Returns:
        A markdown table with one row per CanonicalHook and one column per
        registered frontend, each cell holding that frontend's native hook
        name or "-" if it doesn't fire that hook.
    """
    headers = [spec.display_name for spec in FRONTENDS]
    lines = [
        "| Canonical hook | " + " | ".join(headers) + " |",
        "|---|" + "---|" * len(headers),
    ]
    for hook in CanonicalHook:
        cells = []
        for spec in FRONTENDS:
            registration = spec.protocol.supported_hooks.get(hook)
            cells.append(f"`{registration.native_name}`" if registration is not None else "-")
        lines.append(f"| {hook.value} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _generate_extension_points_table() -> str:
    """Build the extension-points table from the bundled plugins' published hookspecs.

    Returns:
        A markdown table with one row per extension point, its owning plugin,
        its purpose (from its docstring summary), and its return type.
    """
    lines = [
        "| Extension point | Owner | Purpose | Return |",
        "|-----------------|-------|---------|--------|",
    ]
    for info in list_extension_points(_package_plugins(cline_hooks.plugins)):
        return_type = info.return_type.replace("|", "\\|")
        lines.append(f"| `{info.name}({info.params})` | `{info.owner}` | {info.purpose} | `{return_type}` |")
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


class TestReadmeExtensionPoints:
    def test_committed_table_matches_published_extension_points(self) -> None:
        readme = _README_PATH.read_text(encoding="utf-8")
        match = re.search(
            rf"{re.escape(_EXTENSION_POINTS_START)}\n(.*?)\n{re.escape(_EXTENSION_POINTS_END)}",
            readme,
            re.DOTALL,
        )
        assert match is not None, "README is missing the extension-points markers"
        assert match.group(1) == _generate_extension_points_table()
