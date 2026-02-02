"""
Unit tests for PRA metrics infrastructure.
"""

from dazzle_back.metrics import (
    BacklogTracker,
    LatencyHistogram,
    MetricsCollector,
    MetricsReporter,
    ReportFormat,
    ThroughputCounter,
)


class TestLatencyHistogram:
    """Test latency histogram calculations."""

    def test_empty_histogram(self):
        """Empty histogram returns zeros."""
        h = LatencyHistogram(name="test")
        stats = h.stats()
        assert stats.count == 0
        assert stats.p50_ms == 0.0
        assert stats.p99_ms == 0.0

    def test_single_sample(self):
        """Single sample has consistent percentiles."""
        h = LatencyHistogram(name="test")
        h.record(10.0)
        stats = h.stats()
        assert stats.count == 1
        assert stats.min_ms == 10.0
        assert stats.max_ms == 10.0
        assert stats.p50_ms == 10.0

    def test_percentile_calculation(self):
        """Percentiles are calculated correctly."""
        h = LatencyHistogram(name="test")
        # Record 1-100 in order
        for i in range(1, 101):
            h.record(float(i))

        stats = h.stats()
        assert stats.count == 100
        assert stats.min_ms == 1.0
        assert stats.max_ms == 100.0
        assert 49 <= stats.p50_ms <= 51  # Should be around 50
        assert 94 <= stats.p95_ms <= 96  # Should be around 95
        assert 98 <= stats.p99_ms <= 100  # Should be around 99

    def test_reset(self):
        """Reset clears samples and returns final stats."""
        h = LatencyHistogram(name="test")
        h.record(10.0)
        h.record(20.0)

        final = h.reset()
        assert final.count == 2

        after = h.stats()
        assert after.count == 0


class TestThroughputCounter:
    """Test throughput counter calculations."""

    def test_empty_counter(self):
        """Empty counter returns zeros."""
        c = ThroughputCounter(name="test")
        stats = c.stats()
        assert stats.total_count == 0
        assert stats.current_rate == 0.0

    def test_increment(self):
        """Increment increases count."""
        c = ThroughputCounter(name="test")
        c.increment()
        c.increment(5)

        stats = c.stats()
        assert stats.total_count == 6

    def test_rate_calculation(self):
        """Rate is calculated from sliding window."""
        c = ThroughputCounter(name="test", window_seconds=1.0)
        c.increment(100)

        stats = c.stats()
        assert stats.total_count == 100
        # Rate should be positive
        assert stats.current_rate > 0


class TestBacklogTracker:
    """Test backlog tracking."""

    def test_register_consumer(self):
        """Consumer registration creates backlog entry."""
        tracker = BacklogTracker()
        tracker.register_consumer("stream1", "consumer1")

        stats = tracker.get("stream1", "consumer1")
        assert stats is not None
        assert stats.stats().current_lag == 0

    def test_lag_calculation(self):
        """Lag is producer - consumer sequence."""
        tracker = BacklogTracker()
        tracker.register_consumer("stream1", "consumer1")
        tracker.update_producer("stream1", 100)
        tracker.update_consumer("stream1", "consumer1", 80)

        backlog = tracker.get("stream1", "consumer1")
        assert backlog is not None
        assert backlog.current_lag == 20

    def test_multiple_consumers(self):
        """Track multiple consumers on same stream."""
        tracker = BacklogTracker()
        tracker.register_consumer("stream1", "fast")
        tracker.register_consumer("stream1", "slow")

        tracker.update_producer("stream1", 100)
        tracker.update_consumer("stream1", "fast", 95)
        tracker.update_consumer("stream1", "slow", 50)

        fast = tracker.get("stream1", "fast")
        slow = tracker.get("stream1", "slow")

        assert fast.current_lag == 5
        assert slow.current_lag == 50
        assert tracker.total_lag() == 55


class TestMetricsCollector:
    """Test central metrics collector."""

    def test_record_latency(self):
        """Record and retrieve latency."""
        collector = MetricsCollector()
        collector.record_latency("test", 10.0)
        collector.record_latency("test", 20.0)

        stats = collector.get_latency_stats("test")
        assert stats is not None
        assert stats.count == 2

    def test_record_throughput(self):
        """Record and retrieve throughput."""
        collector = MetricsCollector()
        collector.record_throughput("intents", 10)

        stats = collector.get_throughput_stats("intents")
        assert stats is not None
        assert stats.total_count == 10

    def test_record_error(self):
        """Record and retrieve error counts."""
        collector = MetricsCollector()
        collector.record_error("rejection", 5)
        collector.record_error("rejection", 3)

        assert collector.get_error_count("rejection") == 8
        assert collector.get_error_count("unknown") == 0

    def test_snapshot(self):
        """Snapshot contains all metrics."""
        collector = MetricsCollector()
        collector.record_latency("test", 10.0)
        collector.record_throughput("intents")
        collector.record_error("dlq")

        snapshot = collector.snapshot()
        assert "test" in snapshot.latency
        assert "intents" in snapshot.throughput
        assert snapshot.error_counts["dlq"] == 1


class TestMetricsReporter:
    """Test metrics reporter."""

    def test_generate_report(self):
        """Generate report from collector."""
        collector = MetricsCollector()
        collector.record_latency("intent_to_fact", 10.0)
        collector.record_latency("intent_to_fact", 20.0)
        collector.record_throughput("intents", 100)
        collector.record_throughput("facts", 90)

        reporter = MetricsReporter(collector)
        report = reporter.generate_report(profile="test")

        assert report.profile == "test"
        assert report.latency_p50_ms > 0
        assert report.throughput_intents_per_sec >= 0

    def test_format_json(self):
        """Format report as JSON."""
        collector = MetricsCollector()
        reporter = MetricsReporter(collector)
        report = reporter.generate_report()

        json_str = reporter.format_json(report)
        assert '"version": "1.0"' in json_str
        assert '"profile"' in json_str

    def test_format_human(self):
        """Format report as human-readable text."""
        collector = MetricsCollector()
        reporter = MetricsReporter(collector)
        report = reporter.generate_report(profile="test")

        text = reporter.format_human(report)
        assert "DAZZLE PRA PERFORMANCE REPORT" in text
        assert "LATENCY" in text
        assert "THROUGHPUT" in text

    def test_format_markdown(self):
        """Format report as Markdown."""
        collector = MetricsCollector()
        reporter = MetricsReporter(collector)
        report = reporter.generate_report()

        md = reporter.format_markdown(report)
        assert "# PRA Performance Report" in md
        assert "| Percentile | Value |" in md

    def test_format_dispatch(self):
        """Format method dispatches correctly."""
        collector = MetricsCollector()
        reporter = MetricsReporter(collector)
        report = reporter.generate_report()

        json_out = reporter.format(report, ReportFormat.JSON)
        human_out = reporter.format(report, ReportFormat.HUMAN)
        md_out = reporter.format(report, ReportFormat.MARKDOWN)

        assert json_out.startswith("{")
        assert "DAZZLE PRA" in human_out
        assert "# PRA" in md_out
