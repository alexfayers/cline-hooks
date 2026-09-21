from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import cline_hooks.core.daemon_config as daemon_config_module
from cline_hooks.core.daemon_config import DEFAULT_PORT, load_or_create

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def isolate_daemon_config(mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mocker.patch.object(daemon_config_module, "_DAEMON_CONFIG_PATH", tmp_path / "daemon.json")
    monkeypatch.delenv("CLINE_HOOKS_DAEMON_PORT", raising=False)


class TestLoadOrCreate:
    def test_creates_file_with_default_port_when_absent(self) -> None:
        config = load_or_create()
        assert config.port == DEFAULT_PORT
        assert config.token

    def test_writes_mode_0600(self) -> None:
        load_or_create()
        mode = daemon_config_module._DAEMON_CONFIG_PATH.stat().st_mode & 0o777
        assert mode == 0o600

    def test_reuses_existing_token(self) -> None:
        first = load_or_create()
        second = load_or_create()
        assert second.token == first.token

    def test_env_var_overrides_default_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLINE_HOOKS_DAEMON_PORT", "9999")
        assert load_or_create().port == 9999

    def test_invalid_env_var_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLINE_HOOKS_DAEMON_PORT", "not-a-port")
        assert load_or_create().port == DEFAULT_PORT
