"""
Latency histogram for performance measurement.

Provides p50/p95/p99 percentile calculations with efficient
streaming updates using a sorted insertion approach.
"""

from __future__ import annotations

import bisect
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class LatencyStats:
    """Computed latency statistics."""

    count: int
    min_ms: float
    max_ms: float
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    stddev_ms: float


@dataclass
class LatencyHistogram:
    """
    Thread-safe latency histogram with percentile calculations.

    Uses sorted list for accurate percentile computation.
    For high-volume scenarios, consider switching to t-digest or HDR histogram.

    Example:
        histogram = LatencyHistogram(name="intent_to_fact")
        histogram.record(12.5)
        histogram.record(45.2)
        stats = histogram.stats()
        print(f"p99: {stats.p99_ms}ms")
    """

    name: str
    max_samples: int = 10000
    _samples: list[float] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _sum: float = field(default=0.0)
    _sum_sq: float = field(default=0.0)
    _created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def record(self, latency_ms: float) -> None:
        """
        Record a latency measurement.

        Args:
            latency_ms: Latency in milliseconds
        """
        with self._lock:
            # Maintain sorted order for percentile calculation
            bisect.insort(self._samples, latency_ms)

            # Update running stats
            self._sum += latency_ms
            self._sum_sq += latency_ms * latency_ms

            # Trim if exceeding max samples (remove from middle to maintain distribution)
            if len(self._samples) > self.max_samples:
                mid = len(self._samples) // 2
                removed = self._samples.pop(mid)
                self._sum -= removed
                self._sum_sq -= removed * removed

    def stats(self) -> LatencyStats:
        """
        Compute latency statistics.

        Returns:
            LatencyStats with count, min, max, mean, percentiles, stddev
        """
        with self._lock:
            if not self._samples:
                return LatencyStats(
                    count=0,
                    min_ms=0.0,
                    max_ms=0.0,
                    mean_ms=0.0,
                    p50_ms=0.0,
                    p95_ms=0.0,
                    p99_ms=0.0,
                    stddev_ms=0.0,
                )

            n = len(self._samples)
            mean = self._sum / n

            # Variance calculation
            variance = (self._sum_sq / n) - (mean * mean)
            stddev = variance**0.5 if variance > 0 else 0.0

            return LatencyStats(
                count=n,
                min_ms=self._samples[0],
                max_ms=self._samples[-1],
                mean_ms=mean,
                p50_ms=self._percentile(50),
                p95_ms=self._percentile(95),
                p99_ms=self._percentile(99),
                stddev_ms=stddev,
            )

    def _percentile(self, p: float) -> float:
        """Calculate percentile from sorted samples (must hold lock)."""
        if not self._samples:
            return 0.0

        n = len(self._samples)
        idx = (p / 100.0) * (n - 1)
        lower = int(idx)
        upper = min(lower + 1, n - 1)
        weight = idx - lower

        return self._samples[lower] * (1 - weight) + self._samples[upper] * weight

    def reset(self) -> LatencyStats:
        """
        Reset histogram and return final stats.

        Returns:
            Final statistics before reset
        """
        with self._lock:
            # Compute stats inline to avoid deadlock
            if not self._samples:
                stats = LatencyStats(
                    count=0,
                    min_ms=0.0,
                    max_ms=0.0,
                    mean_ms=0.0,
                    p50_ms=0.0,
                    p95_ms=0.0,
                    p99_ms=0.0,
                    stddev_ms=0.0,
                )
            else:
                n = len(self._samples)
                mean = self._sum / n
                variance = (self._sum_sq / n) - (mean * mean)
                stddev = variance**0.5 if variance > 0 else 0.0
                stats = LatencyStats(
                    count=n,
                    min_ms=self._samples[0],
                    max_ms=self._samples[-1],
                    mean_ms=mean,
                    p50_ms=self._percentile(50),
                    p95_ms=self._percentile(95),
                    p99_ms=self._percentile(99),
                    stddev_ms=stddev,
                )

            self._samples.clear()
            self._sum = 0.0
            self._sum_sq = 0.0
            self._created_at = datetime.now(UTC)
            return stats

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        stats = self.stats()
        return {
            "name": self.name,
            "count": stats.count,
            "min_ms": round(stats.min_ms, 3),
            "max_ms": round(stats.max_ms, 3),
            "mean_ms": round(stats.mean_ms, 3),
            "p50_ms": round(stats.p50_ms, 3),
            "p95_ms": round(stats.p95_ms, 3),
            "p99_ms": round(stats.p99_ms, 3),
            "stddev_ms": round(stats.stddev_ms, 3),
        }


@dataclass
class LatencyTracker:
    """
    Track latencies across multiple named histograms.

    Example:
        tracker = LatencyTracker()
        tracker.record("intent_to_fact", 12.5)
        tracker.record("fact_to_projection", 3.2)
        report = tracker.all_stats()
    """

    _histograms: dict[str, LatencyHistogram] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def record(self, name: str, latency_ms: float) -> None:
        """Record latency for a named histogram."""
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = LatencyHistogram(name=name)

        self._histograms[name].record(latency_ms)

    def get(self, name: str) -> LatencyHistogram | None:
        """Get histogram by name."""
        return self._histograms.get(name)

    def all_stats(self) -> dict[str, LatencyStats]:
        """Get stats for all histograms."""
        return {name: h.stats() for name, h in self._histograms.items()}

    def to_dict(self) -> dict[str, Any]:
        """Serialize all histograms."""
        return {name: h.to_dict() for name, h in self._histograms.items()}

    def reset_all(self) -> dict[str, LatencyStats]:
        """Reset all histograms and return final stats."""
        return {name: h.reset() for name, h in self._histograms.items()}
