"""
Regression tests for HotReloadManager wiring (#834).

The module at src/dazzle_ui/runtime/hot_reload.py was imported by nothing
prior to cycle 328 — it was half-shipped behind the combined_server
`enable_watch` flag but never actually instantiated. These tests pin the
wiring: constructing a manager from a project root, starting/stopping its
watchers, and registering SSE clients.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from dazzle_ui.runtime.hot_reload import (
    FileWatcher,
    HotReloadManager,
    create_reload_callback,
)


class TestFileWatcher:
    def test_start_stop_roundtrip(self, tmp_path: Path) -> None:
        """A watcher starts a daemon thread, runs briefly, and stops cleanly."""
        (tmp_path / "example.dsl").write_text("module t\n")
        seen: list[Path] = []
        watcher = FileWatcher(
            paths=[tmp_path],
            on_change=seen.append,
            patterns=["*.dsl"],
            poll_interval=0.05,
        )
        watcher.start()
        try:
            assert watcher._thread is not None
            assert watcher._thread.is_alive()
        finally:
            watcher.stop()
        assert not watcher._thread.is_alive()

    def test_detects_modification(self, tmp_path: Path) -> None:
        target = tmp_path / "example.dsl"
        target.write_text("module t\n")
        changed: list[Path] = []
        evt = threading.Event()

        def on_change(p: Path) -> None:
            changed.append(p)
            evt.set()

        watcher = FileWatcher(
            paths=[tmp_path],
            on_change=on_change,
            patterns=["*.dsl"],
            poll_interval=0.05,
        )
        watcher.start()
        try:
            # Give the watcher one poll cycle to snapshot mtimes
            import time

            time.sleep(0.1)
            # Bump mtime via rewrite
            target.write_text("module t\nmodule t2\n")
            # Touch mtime forward so the check beats filesystem granularity
            import os as _os

            _os.utime(target, None)
            assert evt.wait(timeout=2.0), "watcher never fired"
        finally:
            watcher.stop()
        assert target in changed


class TestHotReloadManager:
    def test_construction_without_starting(self, tmp_path: Path) -> None:
        manager = HotReloadManager(project_root=tmp_path)
        assert manager.project_root == tmp_path
        assert manager._watcher is None
        assert manager._source_watcher is None

    def test_start_stop_with_no_paths_does_not_raise(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No DSL files present → warning + no watcher; stop is still safe."""
        manager = HotReloadManager(project_root=tmp_path)
        manager.start()
        captured = capsys.readouterr()
        assert "No DSL files found" in captured.out
        assert manager._watcher is None
        manager.stop()  # must not raise

    def test_start_stop_with_dsl_dir(self, tmp_path: Path) -> None:
        dsl_dir = tmp_path / "dsl"
        dsl_dir.mkdir()
        (dsl_dir / "app.dsl").write_text("module t\n")
        manager = HotReloadManager(project_root=tmp_path)
        manager.start()
        try:
            assert manager._watcher is not None
        finally:
            manager.stop()
        assert manager._watcher is None

    def test_sse_client_register_unregister(self, tmp_path: Path) -> None:
        manager = HotReloadManager(project_root=tmp_path)
        event = manager.register_sse_client()
        assert event in manager._sse_clients
        manager.unregister_sse_client(event)
        assert event not in manager._sse_clients

    def test_notify_sets_all_registered_events(self, tmp_path: Path) -> None:
        manager = HotReloadManager(project_root=tmp_path)
        events = [manager.register_sse_client() for _ in range(3)]
        manager._notify_clients()
        assert all(e.is_set() for e in events)


class TestCreateReloadCallback:
    def test_returns_callable(self, tmp_path: Path) -> None:
        cb = create_reload_callback(tmp_path)
        assert callable(cb)

    def test_callback_returns_none_on_empty_project(self, tmp_path: Path) -> None:
        """No dazzle.toml → manifest load raises → callback returns None."""
        cb = create_reload_callback(tmp_path)
        result = cb()
        assert result is None


class TestCombinedServerWiring:
    """Structural test: combined_server references HotReloadManager."""

    def test_combined_server_imports_hot_reload(self) -> None:
        """run_unified_server must import HotReloadManager when enable_watch is true."""
        source = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "dazzle_ui"
            / "runtime"
            / "combined_server.py"
        ).read_text()
        assert "from dazzle_ui.runtime.hot_reload import" in source
        assert "HotReloadManager" in source
        assert "create_reload_callback" in source
        # The F841 "reserved for future use" markers must be gone — this is
        # the ratchet that fires if someone re-suppresses the flags.
        assert "noqa: F841" not in source
