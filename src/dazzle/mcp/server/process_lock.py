"""Single-instance guard for the DAZZLE MCP server.

A second `dazzle mcp run` against the same project root would race the first on
the SQLite WAL of `.dazzle/knowledge_graph.db` — long enough on a cold seed to
exceed Claude Code's 30s MCP handshake timeout. The guard takes a non-blocking
fcntl lock so the second instance fails immediately with a message naming the
holder, instead of hanging.

Lock file format (JSON, written by the holder on acquire):

    {"pid": 12345, "started_at": 1716624000.0, "working_dir": "/path/to/project"}

A stale lock (PID no longer alive) is silently taken over.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO

logger = logging.getLogger(__name__)

_LOCK_FILENAME = "mcp.lock"


@dataclass(frozen=True)
class LockConflict:
    """Details of an existing live holder."""

    pid: int
    started_at: float | None
    working_dir: str | None


class ProcessLock:
    """Non-blocking single-instance lock keyed by project root.

    Usage:
        lock = ProcessLock(project_root)
        conflict = lock.acquire()
        if conflict is not None:
            # another process holds it
            ...
        try:
            ...
        finally:
            lock.release()
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.lock_path = project_root / ".dazzle" / _LOCK_FILENAME
        self._fd: IO[str] | None = None

    def acquire(self) -> LockConflict | None:
        """Try to take the lock.

        Returns None on success. Returns a LockConflict describing the live
        holder on failure. A stale lock (PID gone) is taken over and counted
        as success.
        """
        if sys.platform == "win32":
            # No-op on Windows; fcntl is unavailable and Dazzle's primary
            # platforms are macOS/Linux.
            return None

        # Test-only escape hatch: integration tests legitimately need to
        # spawn multiple servers in the same project root to exercise the
        # subprocess code path. Not for production use.
        if os.environ.get("DAZZLE_MCP_SKIP_LOCK") == "1":
            return None

        import fcntl

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        # Open in r+ if exists, else w+. Keep fd open for the process lifetime.
        try:
            fd = open(self.lock_path, "r+", encoding="utf-8")
        except FileNotFoundError:
            fd = open(self.lock_path, "w+", encoding="utf-8")

        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                conflict = _read_holder(fd)
                fd.close()
                if conflict is None or not _pid_alive(conflict.pid):
                    # Stale: retry once by removing and re-creating.
                    return self._take_over_stale()
                return conflict
            fd.close()
            raise

        # Got the lock — write our metadata.
        fd.seek(0)
        fd.truncate()
        json.dump(
            {
                "pid": os.getpid(),
                "started_at": time.time(),
                "working_dir": str(self.project_root),
            },
            fd,
        )
        fd.flush()
        self._fd = fd
        return None

    def _take_over_stale(self) -> LockConflict | None:
        """Remove a stale lock file and try once more.

        Only called after we've already observed the holder PID is dead.
        Returns None on success or a LockConflict if a third process raced
        us into the slot.
        """
        import fcntl

        try:
            self.lock_path.unlink()
        except FileNotFoundError:
            pass

        fd = open(self.lock_path, "w+", encoding="utf-8")
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                conflict = _read_holder(fd)
                fd.close()
                return conflict or LockConflict(pid=-1, started_at=None, working_dir=None)
            fd.close()
            raise

        json.dump(
            {
                "pid": os.getpid(),
                "started_at": time.time(),
                "working_dir": str(self.project_root),
            },
            fd,
        )
        fd.flush()
        self._fd = fd
        return None

    def release(self) -> None:
        """Release the lock if held."""
        if self._fd is None:
            return
        if sys.platform != "win32":
            import fcntl

            try:
                fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        try:
            self._fd.close()
        except OSError:
            pass
        self._fd = None
        # Best-effort cleanup; another instance may have re-acquired by now.
        try:
            self.lock_path.unlink()
        except (FileNotFoundError, OSError):
            pass


def _read_holder(fd: IO[str]) -> LockConflict | None:
    """Read holder metadata from an open lock file. Returns None on parse error."""
    try:
        fd.seek(0)
        raw = fd.read()
        if not raw.strip():
            return None
        data = json.loads(raw)
        return LockConflict(
            pid=int(data["pid"]),
            started_at=data.get("started_at"),
            working_dir=data.get("working_dir"),
        )
    except (OSError, ValueError, KeyError):
        return None


def _pid_alive(pid: int) -> bool:
    """Return True if `pid` names a live process. `kill -0` semantics."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it — still counts as alive.
        return True
    except OSError:
        return False
    return True


def format_conflict_message(conflict: LockConflict, project_root: Path) -> str:
    """Render a human-readable failure message for stderr."""
    lines = [
        f"Another DAZZLE MCP server is already running for {project_root}.",
        f"  PID:     {conflict.pid}",
    ]
    if conflict.started_at:
        age = time.time() - conflict.started_at
        lines.append(
            f"  Started: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(conflict.started_at))} ({_format_age(age)} ago)"
        )
    if conflict.working_dir:
        lines.append(f"  Cwd:     {conflict.working_dir}")
    lines.append("")
    lines.append(f"To release: kill {conflict.pid}")
    # A single global MCP rooted at a framework checkout pins one project root
    # for *every* session, so the second session to boot can't acquire this
    # per-root lock (#1374). If this root is a framework checkout, nudge toward
    # a project-scoped config, which gets its own lock + KG and sidesteps this.
    try:
        from .state import _detect_dev_environment

        is_framework_checkout = _detect_dev_environment(project_root)
    except Exception:
        # Never let a guidance hint break the (already-failing) boot path.
        logger.debug("dev-environment probe for conflict hint failed", exc_info=True)
        is_framework_checkout = False
    if is_framework_checkout:
        lines.append("")
        lines.append(
            "This root is a framework checkout. If you meant to work on a "
            "specific project, point the MCP at that project's directory "
            "(--working-dir <project>) so it gets its own lock, knowledge "
            "graph, and pinned version rather than sharing this global one."
        )
    return "\n".join(lines)


def _format_age(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}m"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h"
    return f"{int(seconds / 86400)}d"
