from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pytest

from cline_hooks.core.daemon_config import DaemonConfig
from cline_hooks.daemon.client import probe_healthz
from cline_hooks.daemon.server import make_server

if TYPE_CHECKING:
    from collections.abc import Iterator
    from http.server import ThreadingHTTPServer


@pytest.fixture
def running_daemon() -> Iterator[ThreadingHTTPServer]:
    server = make_server(DaemonConfig(port=0, token="secret-token"), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class TestProbeHealthz:
    def test_returns_the_healthz_body_for_a_real_daemon(self, running_daemon: ThreadingHTTPServer) -> None:
        port = running_daemon.server_address[1]
        health = probe_healthz(port)
        assert health is not None
        assert "plugin_fingerprint" in health

    def test_returns_none_when_nothing_is_listening(self, running_daemon: ThreadingHTTPServer) -> None:
        dead_port = running_daemon.server_address[1]
        running_daemon.shutdown()
        running_daemon.server_close()
        assert probe_healthz(dead_port) is None
