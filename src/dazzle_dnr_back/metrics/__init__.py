"""
Metrics infrastructure for Dazzle Performance Reference App.

Provides time-series collection, latency histograms, throughput counters,
and consumer lag tracking for event-first architecture performance analysis.
"""

from .backlog import BacklogTracker
from .collector import MetricsCollector
from .latency import LatencyHistogram
from .reporter import MetricsReporter, ReportFormat
from .throughput import ThroughputCounter

__all__ = [
    "BacklogTracker",
    "LatencyHistogram",
    "MetricsCollector",
    "MetricsReporter",
    "ReportFormat",
    "ThroughputCounter",
]
