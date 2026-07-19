"""#1628 multi-session MCP state isolation and lock doctor."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from dazzle.mcp.lock_doctor import (
    clear_stale_project_locks,
    diagnose_project_mcp,
)
from dazzle.mcp.server import mcp_session as ms
from dazzle.mcp.server.process_lock import (
    EXIT_LOCK_CONTENTION,
    ProcessLock,
    _pid_alive,
    clear_stale_lock,
    diagnose_lock,
    format_conflict_message,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="fcntl lock is no-op on Windows")


class TestMcpSessionPaths:
    def test_default_is_not_shared(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DAZZLE_MCP_SHARED", raising=False)
        assert ms.mcp_shared_mode() is False
        assert ms.exclusive_lock_required() is False

    def test_shared_mode_enables_exclusive_lock(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DAZZLE_MCP_SHARED", "1")
        monkeypatch.delenv("DAZZLE_MCP_SKIP_LOCK", raising=False)
        assert ms.mcp_shared_mode() is True
        assert ms.exclusive_lock_required() is True

    def test_skip_lock_disables_exclusive_even_in_shared(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DAZZLE_MCP_SHARED", "1")
        monkeypatch.setenv("DAZZLE_MCP_SKIP_LOCK", "1")
        assert ms.exclusive_lock_required() is False

    def test_session_dirs_are_isolated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DAZZLE_MCP_SHARED", raising=False)
        monkeypatch.setenv("DAZZLE_MCP_SESSION_ID", "alice")
        dir_a = ms.mcp_state_dir(tmp_path)
        kg_a = ms.mcp_kg_db_path(tmp_path)
        assert dir_a == tmp_path / ".dazzle" / "mcp-sessions" / "alice"
        assert kg_a == dir_a / "knowledge_graph.db"

        monkeypatch.setenv("DAZZLE_MCP_SESSION_ID", "bob")
        dir_b = ms.mcp_state_dir(tmp_path)
        assert dir_b == tmp_path / ".dazzle" / "mcp-sessions" / "bob"
        assert dir_a != dir_b

    def test_shared_mode_uses_legacy_dazzle_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DAZZLE_MCP_SHARED", "1")
        assert ms.mcp_state_dir(tmp_path) == tmp_path / ".dazzle"
        assert ms.mcp_kg_db_path(tmp_path) == tmp_path / ".dazzle" / "knowledge_graph.db"
        assert ms.mcp_lock_path(tmp_path) == tmp_path / ".dazzle" / "mcp.lock"

    def test_two_sessions_can_hold_state_concurrently(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Acceptance: two concurrent contexts on same monorepo path.

        Multi-session default does not take exclusive lock; each session
        writes its own KG path so no WAL race on a shared file.
        """
        monkeypatch.delenv("DAZZLE_MCP_SHARED", raising=False)

        monkeypatch.setenv("DAZZLE_MCP_SESSION_ID", "s1")
        p1 = ms.mcp_kg_db_path(tmp_path)
        p1.parent.mkdir(parents=True, exist_ok=True)
        p1.write_text("session-1")

        monkeypatch.setenv("DAZZLE_MCP_SESSION_ID", "s2")
        p2 = ms.mcp_kg_db_path(tmp_path)
        p2.parent.mkdir(parents=True, exist_ok=True)
        p2.write_text("session-2")

        assert p1 != p2
        assert p1.read_text() == "session-1"
        assert p2.read_text() == "session-2"
        # Default: exclusive lock not required — second process would not exit 2
        assert ms.exclusive_lock_required() is False


class TestSharedModeExclusiveLock:
    def test_shared_mode_still_rejects_second_holder(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DAZZLE_MCP_SHARED", "1")
        monkeypatch.delenv("DAZZLE_MCP_SKIP_LOCK", raising=False)
        lock_path = ms.mcp_lock_path(tmp_path)
        first = ProcessLock(tmp_path, lock_path=lock_path)
        assert first.acquire() is None
        try:
            second = ProcessLock(tmp_path, lock_path=lock_path)
            conflict = second.acquire()
            assert conflict is not None
            assert conflict.pid == os.getpid()
        finally:
            first.release()

    def test_multi_session_lock_paths_do_not_collide(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even if someone acquires session locks, different session ids differ."""
        monkeypatch.delenv("DAZZLE_MCP_SHARED", raising=False)
        monkeypatch.setenv("DAZZLE_MCP_SESSION_ID", "a")
        path_a = ms.mcp_lock_path(tmp_path)
        monkeypatch.setenv("DAZZLE_MCP_SESSION_ID", "b")
        path_b = ms.mcp_lock_path(tmp_path)
        assert path_a != path_b

        lock_a = ProcessLock(tmp_path, lock_path=path_a)
        lock_b = ProcessLock(tmp_path, lock_path=path_b)
        assert lock_a.acquire() is None
        try:
            assert lock_b.acquire() is None
        finally:
            lock_a.release()
            lock_b.release()


class TestLockDoctor:
    def test_diagnose_absent(self, tmp_path: Path) -> None:
        d = diagnose_lock(tmp_path / "mcp.lock")
        assert d.classification == "absent"
        assert d.exists is False

    def test_diagnose_stale_and_clear(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "mcp.lock"
        dead = _find_dead_pid()
        lock_path.write_text(
            json.dumps({"pid": dead, "started_at": time.time() - 99, "working_dir": str(tmp_path)})
        )
        d = diagnose_lock(lock_path)
        assert d.classification == "stale"
        assert d.pid_alive is False
        changed, msg = clear_stale_lock(lock_path)
        assert changed is True
        assert "Cleared" in msg
        assert not lock_path.exists()

    def test_refuse_clear_live(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "mcp.lock"
        lock = ProcessLock(tmp_path, lock_path=lock_path)
        assert lock.acquire() is None
        try:
            changed, msg = clear_stale_lock(lock_path)
            assert changed is False
            assert f"LOCK_HELD_BY_PID={os.getpid()}" in msg
        finally:
            lock.release()

    def test_diagnose_project_lists_sessions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DAZZLE_MCP_SHARED", raising=False)
        monkeypatch.setenv("DAZZLE_MCP_SESSION_ID", "sess1")
        kg = ms.mcp_kg_db_path(tmp_path)
        kg.parent.mkdir(parents=True, exist_ok=True)
        kg.write_bytes(b"")
        info = diagnose_project_mcp(tmp_path)
        assert info["multi_session_default"] is True
        ids = {s["id"] for s in info["sessions"]}
        assert "sess1" in ids

    def test_clear_stale_project_locks(self, tmp_path: Path) -> None:
        (tmp_path / ".dazzle").mkdir()
        dead = _find_dead_pid()
        lock_path = tmp_path / ".dazzle" / "mcp.lock"
        lock_path.write_text(json.dumps({"pid": dead, "started_at": 1.0}))
        msgs = clear_stale_project_locks(tmp_path)
        assert any("cleared" in m for m in msgs)
        assert not lock_path.exists()


class TestConflictMessageAndExitCode:
    def test_message_has_structured_lock_line(self, tmp_path: Path) -> None:
        from dazzle.mcp.server.process_lock import LockConflict

        conflict = LockConflict(pid=4242, started_at=time.time() - 120, working_dir=str(tmp_path))
        msg = format_conflict_message(conflict, tmp_path)
        assert "LOCK_HELD_BY_PID=4242" in msg
        assert "age=" in msg
        assert "mcp-sessions" in msg or "DAZZLE_MCP_SHARED" in msg
        assert EXIT_LOCK_CONTENTION == 2


def _find_dead_pid() -> int:
    for candidate in range(2**22, 2**22 + 1000):
        if not _pid_alive(candidate):
            return candidate
    raise RuntimeError("Could not find a dead PID for the test")
