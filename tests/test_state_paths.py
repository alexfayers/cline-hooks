from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir
import pytest

from cline_hooks.state.paths import get_data_dir


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A throwaway HOME with no data directory env var, and the shared root inside it."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LLM_PROMPTS_HOME", str(tmp_path / "shared"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("CLINE_HOOKS_DATA_DIR", raising=False)
    return tmp_path


def _old_dir() -> Path:
    return Path(user_data_dir("cline-hooks"))


def test_the_data_dir_env_var_overrides_the_shared_root(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    override = home / "custom" / "state"
    monkeypatch.setenv("CLINE_HOOKS_DATA_DIR", str(override))

    assert get_data_dir() == override
    assert override.is_dir()


def test_the_data_dir_is_the_state_folder_of_cline_hooks_under_the_shared_root(home: Path) -> None:
    assert get_data_dir() == home / "shared" / "cline-hooks" / "state"
    assert get_data_dir().is_dir()


def test_old_files_are_copied_to_the_shared_root_and_kept(home: Path) -> None:
    old = _old_dir()
    old.mkdir(parents=True)
    (old / "hook-state.json").write_text("{}", encoding="utf-8")

    assert get_data_dir() == home / "shared" / "cline-hooks" / "state"
    assert (get_data_dir() / "hook-state.json").read_text(encoding="utf-8") == "{}"
    assert (old / "hook-state.json").is_file()


def test_a_non_empty_shared_root_folder_is_used_as_it_is(home: Path) -> None:
    old = _old_dir()
    old.mkdir(parents=True)
    (old / "hook-state.json").write_text("old", encoding="utf-8")
    new = home / "shared" / "cline-hooks" / "state"
    new.mkdir(parents=True)
    (new / "agents-state.json").write_text("new", encoding="utf-8")

    assert get_data_dir() == new
    assert sorted(path.name for path in new.iterdir()) == ["agents-state.json"]


def test_the_old_folder_stays_in_use_while_the_copy_fails(home: Path) -> None:
    old = _old_dir()
    old.mkdir(parents=True)
    (old / "hook-state.json").write_text("old", encoding="utf-8")
    (home / "shared").mkdir()
    (home / "shared" / "cline-hooks").write_text("in the way", encoding="utf-8")

    assert get_data_dir() == old
