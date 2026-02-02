"""
Backlog tracker for consumer lag measurement.

Tracks the difference between produced and consumed sequence numbers
to measure consumer lag and backpressure.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BacklogStats:
    """Computed backlog statistics for a stream."""

    stream: str
    consumer: str
    current_lag: int
    max_lag: int
    avg_lag: float
    producer_sequence: int
    consumer_sequence: int
    samples: int


@dataclass
class ConsumerBacklog:
    """
    Track backlog for a single consumer on a stream.

    Example:
        backlog = ConsumerBacklog(stream="orders_fact", consumer="projection")
        backlog.update_producer(100)
        backlog.update_consumer(95)
        print(f"Lag: {backlog.current_lag}")
    """

    stream: str
    consumer: str
    _producer_seq: int = field(default=0)
    _consumer_seq: int = field(default=0)
    _max_lag: int = field(default=0)
    _lag_sum: int = field(default=0)
    _samples: int = field(default=0)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def current_lag(self) -> int:
        """Current lag (producer - consumer)."""
        with self._lock:
            return max(0, self._producer_seq - self._consumer_seq)

    def update_producer(self, sequence: int) -> None:
        """Update producer sequence number."""
        with self._lock:
            self._producer_seq = max(self._producer_seq, sequence)
            self._record_sample()

    def update_consumer(self, sequence: int) -> None:
        """Update consumer sequence number."""
        with self._lock:
            self._consumer_seq = max(self._consumer_seq, sequence)
            self._record_sample()

    def _record_sample(self) -> None:
        """Record a lag sample (must hold lock)."""
        lag = max(0, self._producer_seq - self._consumer_seq)
        self._lag_sum += lag
        self._samples += 1
        if lag > self._max_lag:
            self._max_lag = lag

    def stats(self) -> BacklogStats:
        """Get backlog statistics."""
        with self._lock:
            avg = self._lag_sum / self._samples if self._samples > 0 else 0.0
            return BacklogStats(
                stream=self.stream,
                consumer=self.consumer,
                current_lag=max(0, self._producer_seq - self._consumer_seq),
                max_lag=self._max_lag,
                avg_lag=avg,
                producer_sequence=self._producer_seq,
                consumer_sequence=self._consumer_seq,
                samples=self._samples,
            )

    def reset(self) -> BacklogStats:
        """Reset statistics (keep sequences)."""
        with self._lock:
            stats = self.stats()
            self._max_lag = 0
            self._lag_sum = 0
            self._samples = 0
            return stats

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        stats = self.stats()
        return {
            "stream": stats.stream,
            "consumer": stats.consumer,
            "current_lag": stats.current_lag,
            "max_lag": stats.max_lag,
            "avg_lag": round(stats.avg_lag, 2),
            "producer_sequence": stats.producer_sequence,
            "consumer_sequence": stats.consumer_sequence,
        }


@dataclass
class BacklogTracker:
    """
    Track backlog across multiple streams and consumers.

    Example:
        tracker = BacklogTracker()
        tracker.update_producer("orders_fact", 100)
        tracker.update_consumer("orders_fact", "projection", 95)
        tracker.update_consumer("orders_fact", "notification", 80)
    """

    _backlogs: dict[str, ConsumerBacklog] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _growth_history: list[tuple[float, str, int]] = field(default_factory=list)
    _max_history: int = field(default=1000)

    def _key(self, stream: str, consumer: str) -> str:
        """Generate key for stream:consumer pair."""
        return f"{stream}:{consumer}"

    def update_producer(self, stream: str, sequence: int) -> None:
        """
        Update producer sequence for a stream.

        Updates all consumers tracking this stream.
        """
        with self._lock:
            for _key, backlog in self._backlogs.items():
                if backlog.stream == stream:
                    backlog.update_producer(sequence)

    def update_consumer(self, stream: str, consumer: str, sequence: int) -> None:
        """Update consumer sequence for a stream:consumer pair."""
        key = self._key(stream, consumer)
        with self._lock:
            if key not in self._backlogs:
                self._backlogs[key] = ConsumerBacklog(stream=stream, consumer=consumer)

        self._backlogs[key].update_consumer(sequence)

        # Record growth history
        lag = self._backlogs[key].current_lag
        with self._lock:
            self._growth_history.append((time.monotonic(), key, lag))
            if len(self._growth_history) > self._max_history:
                self._growth_history.pop(0)

    def register_consumer(self, stream: str, consumer: str) -> None:
        """Register a consumer without updating sequences."""
        key = self._key(stream, consumer)
        with self._lock:
            if key not in self._backlogs:
                self._backlogs[key] = ConsumerBacklog(stream=stream, consumer=consumer)

    def get(self, stream: str, consumer: str) -> ConsumerBacklog | None:
        """Get backlog tracker for a stream:consumer pair."""
        return self._backlogs.get(self._key(stream, consumer))

    def all_stats(self) -> dict[str, BacklogStats]:
        """Get stats for all tracked backlogs."""
        return {key: b.stats() for key, b in self._backlogs.items()}

    def by_stream(self, stream: str) -> dict[str, BacklogStats]:
        """Get stats for all consumers of a stream."""
        return {key: b.stats() for key, b in self._backlogs.items() if b.stream == stream}

    def total_lag(self) -> int:
        """Get total lag across all consumers."""
        return sum(b.current_lag for b in self._backlogs.values())

    def max_lag(self) -> tuple[str, int]:
        """Get the consumer with maximum lag."""
        if not self._backlogs:
            return ("", 0)

        max_key = max(self._backlogs.keys(), key=lambda k: self._backlogs[k].current_lag)
        return (max_key, self._backlogs[max_key].current_lag)

    def growth_rate(self, window_seconds: float = 10.0) -> dict[str, float]:
        """
        Calculate backlog growth rate per consumer over recent window.

        Positive = growing, negative = shrinking.
        """
        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            # Group by key, get first and last in window
            first_last: dict[str, tuple[float, int, float, int]] = {}
            for ts, key, lag in self._growth_history:
                if ts >= cutoff:
                    if key not in first_last:
                        first_last[key] = (ts, lag, ts, lag)
                    else:
                        first_ts, first_lag, _, _ = first_last[key]
                        first_last[key] = (first_ts, first_lag, ts, lag)

        # Calculate rates
        rates: dict[str, float] = {}
        for key, (first_ts, first_lag, last_ts, last_lag) in first_last.items():
            duration = last_ts - first_ts
            if duration > 0:
                rates[key] = (last_lag - first_lag) / duration
            else:
                rates[key] = 0.0

        return rates

    def to_dict(self) -> dict[str, Any]:
        """Serialize all backlogs."""
        return {
            "backlogs": {key: b.to_dict() for key, b in self._backlogs.items()},
            "total_lag": self.total_lag(),
            "growth_rates": self.growth_rate(),
        }

    def reset_all(self) -> dict[str, BacklogStats]:
        """Reset all backlog statistics."""
        return {key: b.reset() for key, b in self._backlogs.items()}
