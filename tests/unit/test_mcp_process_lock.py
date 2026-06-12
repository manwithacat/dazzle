"""Tests for the single-instance MCP server guard."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from dazzle.mcp.server.process_lock import (
    LockConflict,
    ProcessLock,
    _format_age,
    _pid_alive,
    format_conflict_message,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fcntl lock is no-op on Windows")


class TestProcessLockAcquire:
    def test_acquires_on_clean_dir(self, tmp_path: Path) -> None:
        lock = ProcessLock(tmp_path)
        assert lock.acquire() is None
        assert lock.lock_path.exists()
        data = json.loads(lock.lock_path.read_text())
        assert data["pid"] == os.getpid()
        assert data["working_dir"] == str(tmp_path)
        lock.release()

    def test_release_removes_lock_file(self, tmp_path: Path) -> None:
        lock = ProcessLock(tmp_path)
        assert lock.acquire() is None
        lock.release()
        assert not lock.lock_path.exists()

    def test_release_is_idempotent(self, tmp_path: Path) -> None:
        lock = ProcessLock(tmp_path)
        lock.release()  # Never acquired — should be a no-op
        assert lock.acquire() is None
        lock.release()
        lock.release()  # Second release also a no-op

    def test_creates_dazzle_dir_if_missing(self, tmp_path: Path) -> None:
        lock = ProcessLock(tmp_path)
        assert not (tmp_path / ".dazzle").exists()
        assert lock.acquire() is None
        assert (tmp_path / ".dazzle").is_dir()
        lock.release()


class TestProcessLockConflict:
    def test_rejects_when_live_holder(self, tmp_path: Path) -> None:
        first = ProcessLock(tmp_path)
        assert first.acquire() is None
        try:
            second = ProcessLock(tmp_path)
            conflict = second.acquire()
            assert conflict is not None
            assert conflict.pid == os.getpid()
            assert conflict.working_dir == str(tmp_path)
        finally:
            first.release()

    def test_takes_over_stale_lock(self, tmp_path: Path) -> None:
        # Forge a stale lock file pointing at a PID that doesn't exist.
        (tmp_path / ".dazzle").mkdir()
        lock_path = tmp_path / ".dazzle" / "mcp.lock"
        stale_pid = _find_dead_pid()
        lock_path.write_text(
            json.dumps(
                {
                    "pid": stale_pid,
                    "started_at": time.time() - 3600,
                    "working_dir": str(tmp_path),
                }
            )
        )

        lock = ProcessLock(tmp_path)
        assert lock.acquire() is None
        data = json.loads(lock_path.read_text())
        assert data["pid"] == os.getpid()
        lock.release()

    def test_corrupt_lock_file_treated_as_stale(self, tmp_path: Path) -> None:
        (tmp_path / ".dazzle").mkdir()
        lock_path = tmp_path / ".dazzle" / "mcp.lock"
        lock_path.write_text("{not valid json")
        # No flock held — second acquire should succeed.
        lock = ProcessLock(tmp_path)
        assert lock.acquire() is None
        lock.release()


class TestSkipLockEnvVar:
    def test_env_var_bypasses_lock(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        first = ProcessLock(tmp_path)
        assert first.acquire() is None
        try:
            monkeypatch.setenv("DAZZLE_MCP_SKIP_LOCK", "1")
            second = ProcessLock(tmp_path)
            # With the escape hatch set, acquire returns None (no conflict)
            # and never touches the lock file.
            assert second.acquire() is None
        finally:
            first.release()


class TestPidAlive:
    def test_current_pid_is_alive(self) -> None:
        assert _pid_alive(os.getpid())

    def test_dead_pid_is_not_alive(self) -> None:
        assert not _pid_alive(_find_dead_pid())

    def test_negative_pid_is_not_alive(self) -> None:
        assert not _pid_alive(-1)
        assert not _pid_alive(0)


class TestFormatConflictMessage:
    def test_message_names_pid_and_path(self, tmp_path: Path) -> None:
        conflict = LockConflict(pid=12345, started_at=time.time(), working_dir=str(tmp_path))
        msg = format_conflict_message(conflict, tmp_path)
        assert "12345" in msg
        assert str(tmp_path) in msg
        assert "kill 12345" in msg

    def test_message_handles_missing_metadata(self, tmp_path: Path) -> None:
        conflict = LockConflict(pid=99, started_at=None, working_dir=None)
        msg = format_conflict_message(conflict, tmp_path)
        assert "99" in msg
        # Should not raise on missing fields
        assert "kill 99" in msg

    def _make_framework_checkout(self, root: Path) -> None:
        """Build a dir that `_detect_dev_environment` recognises as a checkout."""
        (root / "src" / "dazzle").mkdir(parents=True)
        (root / "examples").mkdir()
        (root / "pyproject.toml").write_text('[project]\nname = "dazzle-dsl"\n')

    def test_framework_checkout_root_gets_project_scoped_hint(self, tmp_path: Path) -> None:
        # #1374: a framework-rooted global MCP collides across sessions; the
        # conflict message must nudge toward a project-scoped config.
        self._make_framework_checkout(tmp_path)
        conflict = LockConflict(pid=321, started_at=None, working_dir=None)
        msg = format_conflict_message(conflict, tmp_path)
        assert "--working-dir" in msg
        assert "framework checkout" in msg

    def test_plain_project_root_gets_no_dev_hint(self, tmp_path: Path) -> None:
        # A normal project root (not a framework checkout) must not get the hint.
        (tmp_path / "dazzle.toml").write_text('[project]\nname = "app"\n')
        conflict = LockConflict(pid=322, started_at=None, working_dir=None)
        msg = format_conflict_message(conflict, tmp_path)
        assert "--working-dir" not in msg

    def test_age_formatting(self) -> None:
        assert _format_age(5) == "5s"
        assert _format_age(120) == "2m"
        assert _format_age(3600 * 3) == "3h"
        assert _format_age(86400 * 2) == "2d"


def _find_dead_pid() -> int:
    """Return a PID that does not name a live process.

    We probe upward from a high number and pick the first dead slot we find.
    """
    for candidate in range(2**22, 2**22 + 1000):
        if not _pid_alive(candidate):
            return candidate
    raise RuntimeError("Could not find a dead PID for the test")
