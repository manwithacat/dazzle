"""
Metrics infrastructure for Dazzle Performance Reference App.

Provides time-series collection, latency histograms, throughput counters,
consumer lag tracking, and unified system observability for all components.
"""

from .backlog import BacklogTracker
from .collector import MetricsCollector
from .latency import LatencyHistogram
from .reporter import MetricsReporter, ReportFormat
from .system_collector import (
    ComponentType,
    MetricType,
    SystemMetricsCollector,
    SystemMetricsSnapshot,
    get_system_collector,
    reset_system_collector,
)
from .throughput import ThroughputCounter

__all__ = [
    # PRA metrics
    "BacklogTracker",
    "LatencyHistogram",
    "MetricsCollector",
    "MetricsReporter",
    "ReportFormat",
    "ThroughputCounter",
    # System-wide metrics
    "ComponentType",
    "MetricType",
    "SystemMetricsCollector",
    "SystemMetricsSnapshot",
    "get_system_collector",
    "reset_system_collector",
]
