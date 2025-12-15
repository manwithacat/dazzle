"""
Central metrics collector for PRA.

Aggregates latency, throughput, and backlog metrics into a unified interface.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from .backlog import BacklogStats, BacklogTracker
from .latency import LatencyStats, LatencyTracker
from .throughput import ThroughputStats, ThroughputTracker


@dataclass
class PRAMetrics:
    """Complete metrics snapshot for PRA."""

    timestamp: datetime
    duration_seconds: float
    latency: dict[str, LatencyStats]
    throughput: dict[str, ThroughputStats]
    backlog: dict[str, BacklogStats]
    error_counts: dict[str, int]
    recovery: dict[str, float]  # rebuild times


@dataclass
class MetricsCollector:
    """
    Central collector for all PRA metrics.

    Provides a unified interface for recording and retrieving metrics.

    Example:
        collector = MetricsCollector()

        # Record latency
        collector.record_latency("intent_to_fact", 12.5)

        # Record throughput
        collector.record_throughput("intents")

        # Record backlog
        collector.update_consumer_lag("orders_fact", "projection", 95)

        # Get snapshot
        metrics = collector.snapshot()
    """

    _latency: LatencyTracker = field(default_factory=LatencyTracker)
    _throughput: ThroughputTracker = field(default_factory=ThroughputTracker)
    _backlog: BacklogTracker = field(default_factory=BacklogTracker)
    _error_counts: dict[str, int] = field(default_factory=dict)
    _recovery_times: dict[str, float] = field(default_factory=dict)
    _started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    _started_mono: float = field(default_factory=time.monotonic)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    # =========================================================================
    # Latency
    # =========================================================================

    def record_latency(self, name: str, latency_ms: float) -> None:
        """
        Record a latency measurement.

        Common names:
        - intent_to_fact: Time from INTENT record to resulting FACT
        - fact_to_projection: Time from FACT to projection update
        - end_to_end: Full intent → derived view update

        Args:
            name: Metric name
            latency_ms: Latency in milliseconds
        """
        self._latency.record(name, latency_ms)

    def record_hop_latency(
        self,
        correlation_id: UUID,
        hop_name: str,
        start_time: datetime,
        end_time: datetime,
    ) -> float:
        """
        Record latency for a processing hop.

        Args:
            correlation_id: Event correlation ID
            hop_name: Name of the hop (e.g., "intent_to_fact")
            start_time: Start timestamp
            end_time: End timestamp

        Returns:
            Latency in milliseconds
        """
        latency_ms = (end_time - start_time).total_seconds() * 1000
        self.record_latency(hop_name, latency_ms)
        return latency_ms

    def get_latency_stats(self, name: str) -> LatencyStats | None:
        """Get latency statistics for a named histogram."""
        histogram = self._latency.get(name)
        return histogram.stats() if histogram else None

    # =========================================================================
    # Throughput
    # =========================================================================

    def record_throughput(self, name: str, count: int = 1) -> None:
        """
        Record throughput event(s).

        Common names:
        - intents: INTENT records produced
        - facts: FACT records produced
        - projections: Projection updates
        - rejections: Rejected INTENTs

        Args:
            name: Metric name
            count: Number of events (default 1)
        """
        self._throughput.increment(name, count)

    def get_throughput_stats(self, name: str) -> ThroughputStats | None:
        """Get throughput statistics for a named counter."""
        counter = self._throughput.get(name)
        return counter.stats() if counter else None

    # =========================================================================
    # Backlog
    # =========================================================================

    def update_producer_sequence(self, stream: str, sequence: int) -> None:
        """Update producer sequence for a stream."""
        self._backlog.update_producer(stream, sequence)

    def update_consumer_sequence(self, stream: str, consumer: str, sequence: int) -> None:
        """Update consumer sequence for a stream:consumer pair."""
        self._backlog.update_consumer(stream, consumer, sequence)

    def register_consumer(self, stream: str, consumer: str) -> None:
        """Register a consumer without updating sequences."""
        self._backlog.register_consumer(stream, consumer)

    def get_backlog_stats(self, stream: str, consumer: str) -> BacklogStats | None:
        """Get backlog statistics for a stream:consumer pair."""
        backlog = self._backlog.get(stream, consumer)
        return backlog.stats() if backlog else None

    def get_total_lag(self) -> int:
        """Get total lag across all consumers."""
        return self._backlog.total_lag()

    # =========================================================================
    # Errors
    # =========================================================================

    def record_error(self, error_type: str, count: int = 1) -> None:
        """
        Record an error occurrence.

        Common types:
        - rejection: INTENT rejected
        - dlq: Record sent to DLQ
        - retry: Record retried
        - timeout: Processing timeout

        Args:
            error_type: Error type name
            count: Number of errors (default 1)
        """
        with self._lock:
            self._error_counts[error_type] = self._error_counts.get(error_type, 0) + count

    def get_error_count(self, error_type: str) -> int:
        """Get error count for a type."""
        with self._lock:
            return self._error_counts.get(error_type, 0)

    # =========================================================================
    # Recovery
    # =========================================================================

    def record_recovery_time(self, derivation: str, seconds: float) -> None:
        """
        Record rebuild time for a DERIVATION stream.

        Args:
            derivation: Stream name
            seconds: Rebuild time in seconds
        """
        with self._lock:
            self._recovery_times[derivation] = seconds

    def get_recovery_time(self, derivation: str) -> float | None:
        """Get last recorded rebuild time for a derivation."""
        with self._lock:
            return self._recovery_times.get(derivation)

    # =========================================================================
    # Snapshot & Reset
    # =========================================================================

    def snapshot(self) -> PRAMetrics:
        """
        Get a complete metrics snapshot.

        Returns:
            PRAMetrics with all current statistics
        """
        now = datetime.now(UTC)
        duration = time.monotonic() - self._started_mono

        with self._lock:
            error_counts = dict(self._error_counts)
            recovery_times = dict(self._recovery_times)

        return PRAMetrics(
            timestamp=now,
            duration_seconds=duration,
            latency=self._latency.all_stats(),
            throughput=self._throughput.all_stats(),
            backlog=self._backlog.all_stats(),
            error_counts=error_counts,
            recovery=recovery_times,
        )

    def reset(self) -> PRAMetrics:
        """
        Reset all metrics and return final snapshot.

        Returns:
            Final metrics before reset
        """
        snapshot = self.snapshot()

        self._latency.reset_all()
        self._throughput.reset_all()
        self._backlog.reset_all()

        with self._lock:
            self._error_counts.clear()
            self._recovery_times.clear()
            self._started_at = datetime.now(UTC)
            self._started_mono = time.monotonic()

        return snapshot

    def to_dict(self) -> dict[str, Any]:
        """Serialize all metrics to dictionary."""
        now = datetime.now(UTC)
        duration = time.monotonic() - self._started_mono

        with self._lock:
            error_counts = dict(self._error_counts)
            recovery_times = dict(self._recovery_times)

        return {
            "timestamp": now.isoformat(),
            "duration_seconds": round(duration, 2),
            "latency": self._latency.to_dict(),
            "throughput": self._throughput.to_dict(),
            "backlog": self._backlog.to_dict(),
            "error_counts": error_counts,
            "recovery_times": {k: round(v, 3) for k, v in recovery_times.items()},
        }


# Global collector instance (optional, for convenience)
_collector: MetricsCollector | None = None


def get_collector() -> MetricsCollector:
    """
    Get the global metrics collector.

    Creates one if it doesn't exist.
    """
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


def reset_collector() -> MetricsCollector:
    """Reset the global metrics collector."""
    global _collector
    _collector = MetricsCollector()
    return _collector
