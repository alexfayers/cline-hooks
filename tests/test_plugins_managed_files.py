from __future__ import annotations

import os
import threading
from typing import TYPE_CHECKING

import pytest

import cline_hooks.plugins.managed_files as managed_files_module
from cline_hooks.plugins.managed_files import _get_managed_files

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(managed_files_module, "_managed_files", None)
    monkeypatch.setattr(managed_files_module, "_managed_files_mtime", None)


def _stub_impl(monkeypatch: pytest.MonkeyPatch, manifest_path: Path | None, results: list[set[str]]) -> list[int]:
    calls: list[int] = []

    def _impl() -> set[str]:
        calls.append(1)
        return results[len(calls) - 1]

    monkeypatch.setattr(managed_files_module, "_MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(managed_files_module, "_get_managed_files_impl", _impl)
    return calls


class TestGetManagedFilesCaching:
    def test_reads_the_manifest_on_first_call(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        manifest_path = tmp_path / "installed.json"
        manifest_path.write_text("{}", encoding="utf-8")
        calls = _stub_impl(monkeypatch, manifest_path, [{"/a"}])

        assert _get_managed_files() == {"/a"}
        assert len(calls) == 1

    def test_serves_the_cache_when_the_manifest_is_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manifest_path = tmp_path / "installed.json"
        manifest_path.write_text("{}", encoding="utf-8")
        calls = _stub_impl(monkeypatch, manifest_path, [{"/a"}, {"/should-not-be-seen"}])

        assert _get_managed_files() == {"/a"}
        assert _get_managed_files() == {"/a"}
        assert len(calls) == 1

    def test_re_reads_after_the_manifest_is_modified(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        manifest_path = tmp_path / "installed.json"
        manifest_path.write_text("{}", encoding="utf-8")
        calls = _stub_impl(monkeypatch, manifest_path, [{"/a"}, {"/a", "/b"}])

        assert _get_managed_files() == {"/a"}

        bumped_mtime = manifest_path.stat().st_mtime + 1
        os.utime(manifest_path, (bumped_mtime, bumped_mtime))

        assert _get_managed_files() == {"/a", "/b"}
        assert len(calls) == 2

    def test_re_reads_once_the_manifest_starts_existing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        manifest_path = tmp_path / "installed.json"
        calls: list[int] = []

        def _impl() -> set[str]:
            calls.append(1)
            return {"/a"} if manifest_path.exists() else set()

        monkeypatch.setattr(managed_files_module, "_MANIFEST_PATH", manifest_path)
        monkeypatch.setattr(managed_files_module, "_get_managed_files_impl", _impl)

        assert _get_managed_files() == set()
        assert len(calls) == 1

        manifest_path.write_text("{}", encoding="utf-8")

        assert _get_managed_files() == {"/a"}
        assert len(calls) == 2

    def test_returns_empty_set_when_llm_prompts_is_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(managed_files_module, "_MANIFEST_PATH", None)
        monkeypatch.setattr(managed_files_module, "_get_managed_files_impl", None)

        assert _get_managed_files() == set()

    def test_a_failed_read_does_not_permanently_shadow_a_later_successful_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manifest_path = tmp_path / "installed.json"
        manifest_path.write_text("{}", encoding="utf-8")
        attempts = {"n": 0}

        def _impl() -> set[str]:
            attempts["n"] += 1
            if attempts["n"] == 1:
                msg = "transient read failure"
                raise RuntimeError(msg)
            return {"/a"}

        monkeypatch.setattr(managed_files_module, "_MANIFEST_PATH", manifest_path)
        monkeypatch.setattr(managed_files_module, "_get_managed_files_impl", _impl)

        with pytest.raises(RuntimeError):
            _get_managed_files()

        assert _get_managed_files() == {"/a"}
        assert attempts["n"] == 2


class TestGetManagedFilesConcurrency:
    def test_a_cache_miss_is_not_read_twice_by_concurrent_callers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manifest_path = tmp_path / "installed.json"
        manifest_path.write_text("{}", encoding="utf-8")
        calls: list[int] = []
        entered_impl = threading.Event()
        release_impl = threading.Event()

        def _impl() -> set[str]:
            calls.append(1)
            entered_impl.set()
            release_impl.wait(timeout=5)
            return {"/a"}

        monkeypatch.setattr(managed_files_module, "_MANIFEST_PATH", manifest_path)
        monkeypatch.setattr(managed_files_module, "_get_managed_files_impl", _impl)

        results: dict[str, set[str]] = {}

        def _call(name: str) -> None:
            results[name] = _get_managed_files()

        first = threading.Thread(target=_call, args=("first",))
        first.start()
        assert entered_impl.wait(timeout=5)

        second = threading.Thread(target=_call, args=("second",))
        second.start()
        second.join(timeout=0.2)
        assert second.is_alive()

        release_impl.set()
        first.join(timeout=5)
        second.join(timeout=5)

        assert results == {"first": {"/a"}, "second": {"/a"}}
        assert len(calls) == 1
