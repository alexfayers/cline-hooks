from __future__ import annotations

import importlib.metadata
from typing import TYPE_CHECKING

import pytest

import cline_hooks.daemon.fingerprint as fingerprint_module
from cline_hooks.daemon.fingerprint import cached, compute

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.fixture(autouse=True)
def isolate_cache(mocker: MockerFixture) -> None:
    mocker.patch.object(fingerprint_module, "_cache", None)


class TestCompute:
    def test_returns_a_sha256_hex_digest(self) -> None:
        digest = compute()
        assert len(digest) == 64
        assert all(char in "0123456789abcdef" for char in digest)

    def test_is_deterministic_for_an_unchanged_process(self) -> None:
        assert compute() == compute()

    def test_changes_when_a_distribution_version_changes(self, mocker: MockerFixture) -> None:
        entry_point = mocker.Mock()
        entry_point.dist.name = "a-plugin-package"
        entry_point.dist.version = "1.0.0"
        mocker.patch.object(importlib.metadata, "entry_points", return_value=[entry_point])
        before = compute()

        entry_point.dist.version = "2.0.0"
        after = compute()

        assert before != after


class TestCached:
    def test_matches_a_fresh_compute(self) -> None:
        assert cached() == compute()

    def test_does_not_recompute_within_the_cache_window(self, mocker: MockerFixture) -> None:
        first = cached()
        compute_spy = mocker.patch.object(fingerprint_module, "compute", return_value="different-value")

        second = cached()

        compute_spy.assert_not_called()
        assert second == first
