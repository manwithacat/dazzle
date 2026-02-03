"""
Log storage using Redis lists with automatic expiration.

Stores logs in Redis lists with automatic trimming to manage memory.
Supports filtering by source and log level.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from redis import Redis

logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """A single log entry."""

    timestamp: float
    source: str  # e.g., "app", "worker", "celery"
    level: str  # INFO, WARNING, ERROR, DEBUG
    message: str
    raw: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "level": self.level,
            "message": self.message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LogEntry:
        return cls(
            timestamp=data["timestamp"],
            source=data["source"],
            level=data["level"],
            message=data["message"],
            metadata=data.get("metadata", {}),
        )


class LogStore:
    """
    Redis-backed log storage.

    Uses Redis lists for fast append and range queries.
    Automatically trims to max_entries to prevent unbounded growth.
    """

    PREFIX = "dazzle:logs"

    def __init__(
        self,
        redis: Redis[Any],
        max_entries: int = 10000,
    ):
        self._redis = redis
        self._max_entries = max_entries

    def _log_key(self, source_type: str = "all") -> str:
        """Generate Redis key for log list."""
        return f"{self.PREFIX}:{source_type}"

    def append(self, entry: LogEntry) -> None:
        """
        Append a log entry.

        Stores in both the 'all' list and a source-specific list.
        """
        data = json.dumps(entry.to_dict())

        pipe = self._redis.pipeline()
        pipe.lpush(self._log_key("all"), data)
        pipe.ltrim(self._log_key("all"), 0, self._max_entries - 1)

        # Also append to source-specific list for filtering
        if entry.source:
            pipe.lpush(self._log_key(entry.source), data)
            pipe.ltrim(self._log_key(entry.source), 0, self._max_entries - 1)

        # Track by level for quick error access
        if entry.level in ("ERROR", "WARNING"):
            pipe.lpush(self._log_key(entry.level.lower()), data)
            pipe.ltrim(self._log_key(entry.level.lower()), 0, 1000)

        pipe.execute()

    def append_batch(self, entries: list[LogEntry]) -> None:
        """Append multiple log entries efficiently."""
        if not entries:
            return

        pipe = self._redis.pipeline()

        for entry in entries:
            data = json.dumps(entry.to_dict())
            pipe.lpush(self._log_key("all"), data)

            if entry.source:
                pipe.lpush(self._log_key(entry.source), data)

            if entry.level in ("ERROR", "WARNING"):
                pipe.lpush(self._log_key(entry.level.lower()), data)

        # Trim all lists
        pipe.ltrim(self._log_key("all"), 0, self._max_entries - 1)
        for key in ["app", "worker", "celery", "error", "warning"]:
            pipe.ltrim(self._log_key(key), 0, self._max_entries - 1)

        pipe.execute()

    def get_recent(
        self,
        count: int = 100,
        source_type: str = "all",
        level: str | None = None,
    ) -> list[LogEntry]:
        """
        Get recent log entries.

        Args:
            count: Number of entries to retrieve
            source_type: Filter by source type (all, app, worker)
            level: Filter by level (error, warning)

        Returns:
            List of log entries, newest first
        """
        if level and level.lower() in ("error", "warning"):
            key = self._log_key(level.lower())
        else:
            key = self._log_key(source_type)

        raw_entries = self._redis.lrange(key, 0, count - 1)

        entries = []
        for raw in raw_entries:
            try:
                data = json.loads(raw)
                entries.append(LogEntry.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue

        return entries

    def get_error_count(self, duration_seconds: int = 300) -> int:
        """Get count of errors in recent duration."""
        cutoff = time.time() - duration_seconds
        entries = self.get_recent(count=1000, level="error")
        return sum(1 for e in entries if e.timestamp >= cutoff)

    def search(self, query: str, count: int = 100) -> list[LogEntry]:
        """Search logs by message content."""
        entries = self.get_recent(count=self._max_entries)
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        return [e for e in entries if pattern.search(e.message)][:count]


def detect_log_level(message: str) -> str:
    """Detect log level from message content."""
    msg_upper = message.upper()
    if "ERROR" in msg_upper or "EXCEPTION" in msg_upper or "FAILED" in msg_upper:
        return "ERROR"
    elif "WARNING" in msg_upper or "WARN" in msg_upper:
        return "WARNING"
    elif "DEBUG" in msg_upper:
        return "DEBUG"
    return "INFO"


def parse_log_line(line: str) -> LogEntry | None:
    """
    Parse a log line into a LogEntry.

    Supports common Python logging format and Dazzle DNR format.
    """
    if not line or not line.strip():
        return None

    line = line.strip()

    # Try Dazzle DNR format: [timestamp] [source] message
    dnr_match = re.match(
        r"\[(\d{2}:\d{2}:\d{2})\]\s*\[(\w+)\]\s*(.*)",
        line,
    )
    if dnr_match:
        time_str, source, message = dnr_match.groups()
        # Use today's date with the time
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            ts = datetime.fromisoformat(f"{today}T{time_str}").timestamp()
        except ValueError:
            ts = time.time()

        return LogEntry(
            timestamp=ts,
            source=source.lower(),
            level=detect_log_level(message),
            message=message,
            raw=line,
        )

    # Try Python logging format: timestamp - source - level - message
    py_match = re.match(
        r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[,.\d]*)\s+-\s+(\S+)\s+-\s+(\S+)\s+-\s+(.*)",
        line,
    )
    if py_match:
        ts_str, source, level, message = py_match.groups()
        try:
            ts = datetime.fromisoformat(ts_str.replace(",", ".")).timestamp()
        except ValueError:
            ts = time.time()

        return LogEntry(
            timestamp=ts,
            source=source,
            level=level.upper(),
            message=message,
            raw=line,
        )

    # Fallback: treat entire line as message
    return LogEntry(
        timestamp=time.time(),
        source="unknown",
        level=detect_log_level(line),
        message=line,
        raw=line,
    )
