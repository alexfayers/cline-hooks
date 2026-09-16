from __future__ import annotations

import re
from pathlib import Path

from cline_hooks.core.frontends import FRONTENDS
from cline_hooks.core.plugin import list_plugin_methods
from cline_hooks.core.vocabulary import CanonicalHook

_README_PATH = Path(__file__).parent.parent / "README.md"
_MATRIX_START = "<!-- HOOK_MATRIX_START -->"
_MATRIX_END = "<!-- HOOK_MATRIX_END -->"
_PLUGIN_METHODS_START = "<!-- PLUGIN_METHODS_START -->"
_PLUGIN_METHODS_END = "<!-- PLUGIN_METHODS_END -->"


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
            cells.append(
                f"`{registration.native_name}`" if registration is not None else "-"
            )
        lines.append(f"| {hook.value} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _generate_plugin_methods_table() -> str:
    """Build the plugin-methods table from HooksPlugin's introspected methods.

    Returns:
        A markdown table with one row per public HooksPlugin method, its
        purpose (from its docstring summary), and its return type.
    """
    lines = [
        "| Method | Purpose | Return |",
        "|--------|---------|--------|",
    ]
    for info in list_plugin_methods():
        method_cell = f"`{info.name}({info.params})`"
        return_type = info.return_type.replace("|", "\\|")
        lines.append(f"| {method_cell} | {info.purpose} | `{return_type}` |")
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


class TestReadmePluginMethodsTable:
    def test_committed_table_matches_introspected_methods(self) -> None:
        readme = _README_PATH.read_text(encoding="utf-8")
        match = re.search(
            rf"{re.escape(_PLUGIN_METHODS_START)}\n(.*?)\n{re.escape(_PLUGIN_METHODS_END)}",
            readme,
            re.DOTALL,
        )
        assert match is not None, "README is missing the plugin-methods markers"
        assert match.group(1) == _generate_plugin_methods_table()
