"""Unit tests for LockFile — PID-based lock with 15-min TTL."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from dazzle.e2e.errors import ModeAlreadyRunningError
from dazzle.e2e.lifecycle import LockFile


@pytest.fixture
def lock_dir(tmp_path: Path) -> Path:
    d = tmp_path / "example" / ".dazzle"
    d.mkdir(parents=True)
    return d


class TestLockFileAcquire:
    def test_creates_lock_on_empty_dir(self, lock_dir: Path) -> None:
        lock = LockFile(lock_dir / "mode_a.lock")
        lock.acquire("a", lock_dir / "log.log")

        content = json.loads((lock_dir / "mode_a.lock").read_text())
        assert content["pid"] == os.getpid()
        assert content["mode"] == "a"
        assert content["log_file"].endswith("log.log")
        assert "started_at" in content

    def test_raises_when_alive_pid_holds_lock(self, lock_dir: Path) -> None:
        lock_path = lock_dir / "mode_a.lock"
        lock_path.write_text(
            json.dumps(
                {
                    "pid": 99999,
                    "mode": "a",
                    "started_at": "2026-04-13T10:00:00Z",
                    "log_file": "/tmp/x.log",
                }
            )
        )

        lock = LockFile(lock_path)
        with patch("dazzle.e2e.lifecycle.os.kill") as mock_kill:
            mock_kill.return_value = None  # Simulate "alive"
            with patch("dazzle.e2e.lifecycle._iso_now_seconds_ago", return_value=10):
                with pytest.raises(ModeAlreadyRunningError, match="99999"):
                    lock.acquire("a", lock_dir / "log.log")

    def test_deletes_stale_lock_when_pid_dead(self, lock_dir: Path) -> None:
        lock_path = lock_dir / "mode_a.lock"
        lock_path.write_text(
            json.dumps(
                {
                    "pid": 99999,
                    "mode": "a",
                    "started_at": "2026-04-13T10:00:00Z",
                    "log_file": "/tmp/x.log",
                }
            )
        )

        lock = LockFile(lock_path)
        with patch("dazzle.e2e.lifecycle.os.kill", side_effect=ProcessLookupError()):
            lock.acquire("a", lock_dir / "log.log")

        content = json.loads(lock_path.read_text())
        assert content["pid"] == os.getpid()

    def test_deletes_stale_lock_when_older_than_ttl(self, lock_dir: Path) -> None:
        lock_path = lock_dir / "mode_a.lock"
        lock_path.write_text(
            json.dumps(
                {
                    "pid": 99999,
                    "mode": "a",
                    "started_at": "2026-04-13T10:00:00Z",
                    "log_file": "/tmp/x.log",
                }
            )
        )

        lock = LockFile(lock_path, ttl_seconds=900)
        # PID alive, but lock is old
        with patch("dazzle.e2e.lifecycle.os.kill") as mock_kill:
            mock_kill.return_value = None
            with patch("dazzle.e2e.lifecycle._iso_now_seconds_ago", return_value=1000):
                lock.acquire("a", lock_dir / "log.log")

        content = json.loads(lock_path.read_text())
        assert content["pid"] == os.getpid()


class TestLockFileRelease:
    def test_deletes_file(self, lock_dir: Path) -> None:
        lock_path = lock_dir / "mode_a.lock"
        lock = LockFile(lock_path)
        lock.acquire("a", lock_dir / "log.log")
        assert lock_path.exists()

        lock.release()
        assert not lock_path.exists()

    def test_release_is_idempotent_when_already_gone(self, lock_dir: Path) -> None:
        lock = LockFile(lock_dir / "mode_a.lock")
        lock.release()  # Should not raise
        lock.release()  # Still should not raise


class TestLockFileIntegration:
    def test_acquire_release_acquire(self, lock_dir: Path) -> None:
        lock = LockFile(lock_dir / "mode_a.lock")
        lock.acquire("a", lock_dir / "log.log")
        lock.release()
        lock.acquire("a", lock_dir / "log.log")  # Should not raise
        lock.release()

    def test_read_lock_holder(self, lock_dir: Path) -> None:
        lock = LockFile(lock_dir / "mode_a.lock")
        lock.acquire("a", lock_dir / "log.log")

        holder = LockFile(lock_dir / "mode_a.lock").read_holder()
        assert holder is not None
        assert holder["pid"] == os.getpid()
        assert holder["mode"] == "a"


class TestLockFileHolderQueries:
    def test_holder_pid_alive_returns_false_when_no_lock(self, lock_dir: Path) -> None:
        lock = LockFile(lock_dir / "mode_a.lock")
        assert lock.holder_pid_alive() is False

    def test_holder_pid_alive_returns_true_when_current_pid(self, lock_dir: Path) -> None:
        lock = LockFile(lock_dir / "mode_a.lock")
        lock.acquire("a", lock_dir / "log.log")
        assert lock.holder_pid_alive() is True

    def test_holder_age_seconds_returns_small_number_when_just_acquired(
        self, lock_dir: Path
    ) -> None:
        lock = LockFile(lock_dir / "mode_a.lock")
        lock.acquire("a", lock_dir / "log.log")
        age = lock.holder_age_seconds()
        assert age is not None
        assert age >= 0
        assert age < 60  # Just acquired — should be well under a minute

    def test_holder_age_seconds_returns_none_when_no_lock(self, lock_dir: Path) -> None:
        lock = LockFile(lock_dir / "mode_a.lock")
        assert lock.holder_age_seconds() is None
