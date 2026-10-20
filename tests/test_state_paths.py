from __future__ import annotations

from typing import TYPE_CHECKING

from cline_hooks.state.paths import get_data_dir

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_the_data_dir_env_var_overrides_the_platform_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    override = tmp_path / "custom" / "state"
    monkeypatch.setenv("CLINE_HOOKS_DATA_DIR", str(override))

    assert get_data_dir() == override
    assert override.is_dir()
