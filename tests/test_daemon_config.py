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
    @pytest.mark.parametrize(
        ("env_port", "expected"),
        [(None, DEFAULT_PORT), ("9999", 9999), ("not-a-port", DEFAULT_PORT)],
        ids=["default", "override", "invalid"],
    )
    def test_port(self, monkeypatch: pytest.MonkeyPatch, env_port: str | None, expected: int) -> None:
        if env_port is not None:
            monkeypatch.setenv("CLINE_HOOKS_DAEMON_PORT", env_port)
        assert load_or_create().port == expected

    def test_writes_mode_0600(self) -> None:
        load_or_create()
        mode = daemon_config_module._DAEMON_CONFIG_PATH.stat().st_mode & 0o777
        assert mode == 0o600

    def test_keeps_the_token_when_the_port_changes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        first = load_or_create()
        monkeypatch.setenv("CLINE_HOOKS_DAEMON_PORT", "9999")
        second = load_or_create()
        assert first.token
        assert (second.port, second.token) == (9999, first.token)
