"""
Throughput counter for rate measurement.

Provides events-per-second calculations with sliding window averaging.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ThroughputStats:
    """Computed throughput statistics."""

    total_count: int
    current_rate: float  # per second
    peak_rate: float  # per second
    avg_rate: float  # per second over entire period
    duration_seconds: float


@dataclass
class ThroughputCounter:
    """
    Thread-safe throughput counter with rate calculations.

    Uses a sliding window for current rate calculation.

    Example:
        counter = ThroughputCounter(name="intents", window_seconds=5.0)
        counter.increment()
        counter.increment(10)
        stats = counter.stats()
        print(f"Rate: {stats.current_rate}/sec")
    """

    name: str
    window_seconds: float = 5.0
    _count: int = field(default=0)
    _window_counts: list[tuple[float, int]] = field(default_factory=list)
    _peak_rate: float = field(default=0.0)
    _started_at: float = field(default_factory=time.monotonic)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def increment(self, count: int = 1) -> None:
        """
        Increment the counter.

        Args:
            count: Number to add (default 1)
        """
        now = time.monotonic()
        with self._lock:
            self._count += count
            self._window_counts.append((now, count))
            self._prune_window(now)

            # Update peak rate
            current = self._calculate_rate(now)
            if current > self._peak_rate:
                self._peak_rate = current

    def _prune_window(self, now: float) -> None:
        """Remove entries outside the sliding window (must hold lock)."""
        cutoff = now - self.window_seconds
        while self._window_counts and self._window_counts[0][0] < cutoff:
            self._window_counts.pop(0)

    def _calculate_rate(self, now: float) -> float:
        """Calculate current rate from sliding window (must hold lock)."""
        if not self._window_counts:
            return 0.0

        window_total = sum(c for _, c in self._window_counts)
        oldest = self._window_counts[0][0]
        duration = now - oldest

        if duration <= 0:
            return 0.0

        return window_total / duration

    def stats(self) -> ThroughputStats:
        """
        Compute throughput statistics.

        Returns:
            ThroughputStats with count, rates, and duration
        """
        now = time.monotonic()
        with self._lock:
            self._prune_window(now)
            duration = now - self._started_at

            avg_rate = self._count / duration if duration > 0 else 0.0

            return ThroughputStats(
                total_count=self._count,
                current_rate=self._calculate_rate(now),
                peak_rate=self._peak_rate,
                avg_rate=avg_rate,
                duration_seconds=duration,
            )

    def reset(self) -> ThroughputStats:
        """
        Reset counter and return final stats.

        Returns:
            Final statistics before reset
        """
        with self._lock:
            stats = self.stats()
            self._count = 0
            self._window_counts.clear()
            self._peak_rate = 0.0
            self._started_at = time.monotonic()
            return stats

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        stats = self.stats()
        return {
            "name": self.name,
            "total_count": stats.total_count,
            "current_rate": round(stats.current_rate, 2),
            "peak_rate": round(stats.peak_rate, 2),
            "avg_rate": round(stats.avg_rate, 2),
            "duration_seconds": round(stats.duration_seconds, 2),
        }


@dataclass
class ThroughputTracker:
    """
    Track throughput across multiple named counters.

    Example:
        tracker = ThroughputTracker()
        tracker.increment("intents")
        tracker.increment("facts", 5)
        report = tracker.all_stats()
    """

    _counters: dict[str, ThroughputCounter] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def increment(self, name: str, count: int = 1) -> None:
        """Increment a named counter."""
        with self._lock:
            if name not in self._counters:
                self._counters[name] = ThroughputCounter(name=name)

        self._counters[name].increment(count)

    def get(self, name: str) -> ThroughputCounter | None:
        """Get counter by name."""
        return self._counters.get(name)

    def all_stats(self) -> dict[str, ThroughputStats]:
        """Get stats for all counters."""
        return {name: c.stats() for name, c in self._counters.items()}

    def to_dict(self) -> dict[str, Any]:
        """Serialize all counters."""
        return {name: c.to_dict() for name, c in self._counters.items()}

    def reset_all(self) -> dict[str, ThroughputStats]:
        """Reset all counters and return final stats."""
        return {name: c.reset() for name, c in self._counters.items()}
