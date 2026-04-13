"""PID-based lock file with 15-minute TTL safety net.

Matches the pattern used elsewhere in the codebase (e.g., `.dazzle/ux-cycle.lock`).
Stale locks are detected two ways: dead PID (os.kill raises ProcessLookupError)
or file age exceeding the TTL regardless of PID state.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dazzle.e2e.errors import ModeAlreadyRunningError

DEFAULT_TTL_SECONDS = 15 * 60


def _iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_now_seconds_ago(iso_ts: str) -> float:
    """Return seconds between `iso_ts` and now (UTC)."""
    try:
        past = datetime.strptime(iso_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        # Malformed timestamp → treat as ancient.
        return float("inf")
    now = datetime.now(UTC)
    return (now - past).total_seconds()


def _is_pid_alive(pid: int) -> bool:
    """True if the process is still running (POSIX only)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we can't signal it — still alive.
        return True
    return True


class LockFile:
    """JSON-backed PID lock file with stale detection."""

    def __init__(self, path: Path, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.path = path
        self.ttl_seconds = ttl_seconds

    def acquire(self, mode_name: str, log_path: Path) -> None:
        """Acquire the lock.

        Raises ModeAlreadyRunningError if an alive PID holds a non-stale lock.
        Stale locks (dead PID OR age > ttl_seconds) are silently deleted.
        """
        if self.path.exists():
            self._maybe_delete_stale()

        if self.path.exists():
            # Still held by a live process within TTL.
            holder = self.read_holder()
            pid = holder["pid"] if holder else "?"
            raise ModeAlreadyRunningError(
                f"Mode {mode_name} lock held by pid {pid} at {self.path} "
                f"(started {holder.get('started_at') if holder else 'unknown'})"
            )

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "mode": mode_name,
                    "started_at": _iso_now(),
                    "log_file": str(log_path),
                }
            )
        )

    def release(self) -> None:
        """Delete the lock file. No-op if already gone. Does not raise."""
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def read_holder(self) -> dict[str, Any] | None:
        """Return the current lock holder record, or None if absent/malformed."""
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def holder_pid_alive(self) -> bool:
        """True if the current lock holder's PID is alive.

        Returns False if no lock file exists, if the file is malformed,
        if the holder record lacks a pid, or if the PID is dead.
        """
        holder = self.read_holder()
        if holder is None:
            return False
        pid = holder.get("pid")
        if not isinstance(pid, int):
            return False
        return _is_pid_alive(pid)

    def holder_age_seconds(self) -> float | None:
        """Seconds since the lock holder was acquired.

        Returns None if no lock file exists, the file is malformed, or
        the started_at field is missing/invalid.
        """
        holder = self.read_holder()
        if holder is None:
            return None
        started = holder.get("started_at", "")
        if not started:
            return None
        age = _iso_now_seconds_ago(started)
        if age == float("inf"):
            return None
        return age

    # Internals ---------------------------------------------------------------

    def _maybe_delete_stale(self) -> None:
        """Delete the lock if dead PID or older than TTL."""
        holder = self.read_holder()
        if holder is None:
            # Malformed; treat as stale.
            self.release()
            return

        pid = holder.get("pid")
        started_at = holder.get("started_at", "")
        age = _iso_now_seconds_ago(started_at) if started_at else float("inf")

        if age > self.ttl_seconds:
            self.release()
            return
        if not isinstance(pid, int) or not _is_pid_alive(pid):
            self.release()
            return
