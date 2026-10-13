"""
Unified system metrics collector for comprehensive observability.

Aggregates metrics from all system components:
- Event bus (throughput, latency, backlog)
- Database (query latency, connection pool, slow queries)
- HTTP API (request latency, error rates)
- WebSocket (connection count, message rates)

Provides:
- Real-time metrics snapshots
- Historical aggregation
- Prometheus-compatible export
- Integration with ops dashboard
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from threading import Lock
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MetricType(StrEnum):
    """Types of metrics collected."""

    COUNTER = "counter"  # Monotonically increasing
    GAUGE = "gauge"  # Point-in-time value
    HISTOGRAM = "histogram"  # Distribution with percentiles
    SUMMARY = "summary"  # Pre-computed percentiles


class ComponentType(StrEnum):
    """System components being monitored."""

    EVENT_BUS = "event_bus"
    DATABASE = "database"
    HTTP_API = "http_api"
    WEBSOCKET = "websocket"
    CACHE = "cache"
    EXTERNAL_API = "external_api"


@dataclass
class MetricSample:
    """A single metric sample with labels."""

    name: str
    value: float
    timestamp: float
    labels: dict[str, str] = field(default_factory=dict)
    metric_type: MetricType = MetricType.GAUGE


@dataclass
class HistogramBucket:
    """Histogram bucket for distribution tracking."""

    le: float  # Less than or equal threshold
    count: int = 0


@dataclass
class HistogramMetric:
    """Full histogram with buckets and summary stats."""

    name: str
    labels: dict[str, str]
    buckets: list[HistogramBucket]
    count: int = 0
    sum: float = 0.0

    # Pre-computed percentiles
    p50: float = 0.0
    p95: float = 0.0
    p99: float = 0.0


@dataclass
class ComponentMetrics:
    """Metrics for a single component."""

    component: ComponentType
    status: str = "unknown"  # healthy, degraded, unhealthy
    last_check: datetime | None = None

    # Counters
    counters: dict[str, int] = field(default_factory=dict)

    # Gauges
    gauges: dict[str, float] = field(default_factory=dict)

    # Histograms (name -> list of samples for percentile calculation)
    histograms: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    # Recent errors
    errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SystemMetricsSnapshot:
    """Complete snapshot of all system metrics."""

    timestamp: datetime
    uptime_seconds: float
    components: dict[ComponentType, ComponentMetrics]

    # Aggregate stats
    total_requests: int = 0
    total_errors: int = 0
    error_rate: float = 0.0

    # Component health summary
    healthy_count: int = 0
    degraded_count: int = 0
    unhealthy_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "uptime_seconds": self.uptime_seconds,
            "aggregate": {
                "total_requests": self.total_requests,
                "total_errors": self.total_errors,
                "error_rate": self.error_rate,
            },
            "health_summary": {
                "healthy": self.healthy_count,
                "degraded": self.degraded_count,
                "unhealthy": self.unhealthy_count,
            },
            "components": {
                comp.value: {
                    "status": metrics.status,
                    "last_check": metrics.last_check.isoformat() if metrics.last_check else None,
                    "counters": metrics.counters,
                    "gauges": metrics.gauges,
                    "histograms": {
                        name: _compute_histogram_stats(samples)
                        for name, samples in metrics.histograms.items()
                    },
                    "recent_errors": metrics.errors[-10:],  # Last 10 errors
                }
                for comp, metrics in self.components.items()
            },
        }

    def to_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        lines: list[str] = []

        # Uptime
        lines.append("# HELP dazzle_uptime_seconds Time since server start")
        lines.append("# TYPE dazzle_uptime_seconds gauge")
        lines.append(f"dazzle_uptime_seconds {self.uptime_seconds:.2f}")
        lines.append("")

        # Component health
        lines.append(
            "# HELP dazzle_component_health Component health status (1=healthy, 0.5=degraded, 0=unhealthy)"
        )
        lines.append("# TYPE dazzle_component_health gauge")
        for comp, metrics in self.components.items():
            health_value = {"healthy": 1.0, "degraded": 0.5, "unhealthy": 0.0}.get(
                metrics.status, 0.0
            )
            lines.append(f'dazzle_component_health{{component="{comp.value}"}} {health_value}')
        lines.append("")

        # Counters
        for comp, metrics in self.components.items():
            for counter_name, counter_value in metrics.counters.items():
                metric_name = f"dazzle_{comp.value}_{counter_name}_total"
                lines.append(f"# TYPE {metric_name} counter")
                lines.append(f'{metric_name}{{component="{comp.value}"}} {counter_value}')

        # Gauges
        for comp, metrics in self.components.items():
            for gauge_name, gauge_value in metrics.gauges.items():
                metric_name = f"dazzle_{comp.value}_{gauge_name}"
                lines.append(f"# TYPE {metric_name} gauge")
                lines.append(f'{metric_name}{{component="{comp.value}"}} {gauge_value:.2f}')

        # Histograms (as summary with quantiles)
        for comp, metrics in self.components.items():
            for name, samples in metrics.histograms.items():
                if not samples:
                    continue
                stats = _compute_histogram_stats(samples)
                metric_name = f"dazzle_{comp.value}_{name}"
                lines.append(f"# TYPE {metric_name} summary")
                lines.append(
                    f'{metric_name}{{component="{comp.value}",quantile="0.5"}} {stats["p50"]:.2f}'
                )
                lines.append(
                    f'{metric_name}{{component="{comp.value}",quantile="0.95"}} {stats["p95"]:.2f}'
                )
                lines.append(
                    f'{metric_name}{{component="{comp.value}",quantile="0.99"}} {stats["p99"]:.2f}'
                )
                lines.append(f'{metric_name}_count{{component="{comp.value}"}} {stats["count"]}')
                lines.append(f'{metric_name}_sum{{component="{comp.value}"}} {stats["sum"]:.2f}')

        return "\n".join(lines)


def _compute_histogram_stats(samples: list[float]) -> dict[str, float]:
    """Compute histogram statistics from samples."""
    if not samples:
        return {"count": 0, "sum": 0, "p50": 0, "p95": 0, "p99": 0, "min": 0, "max": 0, "avg": 0}

    sorted_samples = sorted(samples)
    n = len(sorted_samples)

    def percentile(p: float) -> float:
        idx = int(n * p)
        return sorted_samples[min(idx, n - 1)]

    return {
        "count": n,
        "sum": sum(samples),
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "p99": percentile(0.99),
        "min": sorted_samples[0],
        "max": sorted_samples[-1],
        "avg": sum(samples) / n,
    }


class SystemMetricsCollector:
    """
    Unified system metrics collector.

    Aggregates metrics from all system components into a single view.
    Thread-safe for concurrent metric recording.

    Example:
        collector = SystemMetricsCollector()

        # Record metrics
        collector.inc_counter(ComponentType.DATABASE, "queries")
        collector.set_gauge(ComponentType.EVENT_BUS, "backlog", 150)
        collector.record_histogram(ComponentType.HTTP_API, "latency_ms", 23.5)

        # Get snapshot
        snapshot = collector.snapshot()
        print(snapshot.to_prometheus())
    """

    # Default histogram buckets for latency (milliseconds)
    DEFAULT_LATENCY_BUCKETS = [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]

    # Maximum samples to keep per histogram
    MAX_HISTOGRAM_SAMPLES = 10000

    def __init__(self) -> None:
        """Initialize the system metrics collector."""
        self._start_time = time.monotonic()
        self._lock = Lock()

        # Component metrics
        self._components: dict[ComponentType, ComponentMetrics] = {
            ct: ComponentMetrics(component=ct) for ct in ComponentType
        }

        # Global counters
        self._total_requests = 0
        self._total_errors = 0

        # Background collection tasks
        self._collection_tasks: list[asyncio.Task[None]] = []
        self._running = False

    def inc_counter(
        self,
        component: ComponentType,
        name: str,
        value: int = 1,
    ) -> None:
        """Increment a counter metric."""
        with self._lock:
            metrics = self._components[component]
            metrics.counters[name] = metrics.counters.get(name, 0) + value

    def set_gauge(
        self,
        component: ComponentType,
        name: str,
        value: float,
    ) -> None:
        """Set a gauge metric value."""
        with self._lock:
            self._components[component].gauges[name] = value

    def record_histogram(
        self,
        component: ComponentType,
        name: str,
        value: float,
    ) -> None:
        """Record a histogram sample."""
        with self._lock:
            samples = self._components[component].histograms[name]
            samples.append(value)

            # Trim if over limit
            if len(samples) > self.MAX_HISTOGRAM_SAMPLES:
                # Keep last N samples
                self._components[component].histograms[name] = samples[
                    -self.MAX_HISTOGRAM_SAMPLES :
                ]

    def record_error(
        self,
        component: ComponentType,
        error_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record an error for a component."""
        with self._lock:
            self._total_errors += 1
            self._components[component].errors.append(
                {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "type": error_type,
                    "message": message,
                    "details": details or {},
                }
            )
            # Keep last 100 errors per component
            if len(self._components[component].errors) > 100:
                self._components[component].errors = self._components[component].errors[-100:]

    def set_component_status(
        self,
        component: ComponentType,
        status: str,
    ) -> None:
        """Set component health status."""
        with self._lock:
            self._components[component].status = status
            self._components[component].last_check = datetime.now(UTC)

    def snapshot(self) -> SystemMetricsSnapshot:
        """Get a snapshot of all current metrics."""
        with self._lock:
            uptime = time.monotonic() - self._start_time

            # Count health statuses
            healthy = sum(1 for m in self._components.values() if m.status == "healthy")
            degraded = sum(1 for m in self._components.values() if m.status == "degraded")
            unhealthy = sum(1 for m in self._components.values() if m.status == "unhealthy")

            # Calculate error rate
            error_rate = (
                self._total_errors / self._total_requests if self._total_requests > 0 else 0.0
            )

            return SystemMetricsSnapshot(
                timestamp=datetime.now(UTC),
                uptime_seconds=uptime,
                components=dict(self._components),
                total_requests=self._total_requests,
                total_errors=self._total_errors,
                error_rate=error_rate,
                healthy_count=healthy,
                degraded_count=degraded,
                unhealthy_count=unhealthy,
            )

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._start_time = time.monotonic()
            self._total_requests = 0
            self._total_errors = 0
            for metrics in self._components.values():
                metrics.counters.clear()
                metrics.gauges.clear()
                metrics.histograms.clear()
                metrics.errors.clear()
                metrics.status = "unknown"
                metrics.last_check = None

    # ========================================================================
    # Component-specific recording helpers
    # ========================================================================

    def record_db_query(
        self,
        query_type: str,
        table: str,
        latency_ms: float,
        rows_affected: int = 0,
    ) -> None:
        """Record a database query metric."""
        self.inc_counter(ComponentType.DATABASE, f"queries_{query_type}")
        self.record_histogram(ComponentType.DATABASE, "query_latency_ms", latency_ms)
        if rows_affected > 0:
            self.inc_counter(ComponentType.DATABASE, "rows_affected", rows_affected)

        # Track slow queries (>100ms)
        if latency_ms > 100:
            self.inc_counter(ComponentType.DATABASE, "slow_queries")

    # ========================================================================
    # Background collection
    # ========================================================================
