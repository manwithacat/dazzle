"""Tests for #1192 slice 1 — the Prometheus scrape endpoint.

``create_metrics_routes`` registers ``GET /_dazzle/metrics``, the
pull-side surface that Prometheus / VictoriaMetrics / Grafana Agent
scrape to ingest Dazzle's runtime telemetry. It is the sibling of the
event / job explorer routes — same ``/_dazzle/*`` prefix, same factory
shape, same auth/gating story (none — debug routes are open by design).

These tests verify:

  * The endpoint returns 200 with the Prometheus exposition
    ``Content-Type: text/plain; version=0.0.4; charset=utf-8``.
  * The body looks like a Prometheus document — ``# HELP`` / ``# TYPE``
    comment lines plus at least one metric sample.
  * When the collector is not wired (``None``), the endpoint still
    returns 200 with a non-error body (the empty Prometheus doc) —
    never 500.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from dazzle.http.metrics.system_collector import (
    ComponentType,
    SystemMetricsCollector,
)
from dazzle.http.runtime.metrics_routes import (
    PROMETHEUS_CONTENT_TYPE,
    create_metrics_routes,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def collector_with_samples() -> SystemMetricsCollector:
    """A collector primed with one counter + one gauge + one histogram."""
    collector = SystemMetricsCollector()
    collector.set_component_status(ComponentType.DATABASE, "healthy")
    collector.inc_counter(ComponentType.DATABASE, "queries_select", 7)
    collector.set_gauge(ComponentType.DATABASE, "connections_active", 4)
    collector.record_histogram(ComponentType.HTTP_API, "request_latency_ms", 12.5)
    collector.record_histogram(ComponentType.HTTP_API, "request_latency_ms", 47.0)
    return collector


@pytest.fixture
def client(collector_with_samples: SystemMetricsCollector) -> TestClient:
    """A TestClient over an app mounting the metrics route."""
    app = FastAPI()
    app.include_router(create_metrics_routes(collector_with_samples))
    return TestClient(app)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_metrics_endpoint_returns_200_with_prometheus_content_type(
    client: TestClient,
) -> None:
    """GET /_dazzle/metrics returns 200 + the standard Prometheus content-type."""
    resp = client.get("/_dazzle/metrics")
    assert resp.status_code == 200
    # The content-type header must match the Prometheus exposition spec
    # exactly, including version and charset — some scrapers are strict.
    assert resp.headers["content-type"] == PROMETHEUS_CONTENT_TYPE


def test_metrics_body_looks_like_prometheus_exposition(client: TestClient) -> None:
    """The body should contain # HELP / # TYPE comment lines + samples."""
    resp = client.get("/_dazzle/metrics")
    body = resp.text
    # At least one HELP and one TYPE line — the uptime metric always emits both.
    assert "# HELP " in body
    assert "# TYPE " in body
    # And at least one metric sample (the uptime gauge is always present).
    assert "dazzle_uptime_seconds " in body
    # Counter we primed in the fixture surfaces with the standard
    # ``_total`` suffix and a component label.
    assert "dazzle_database_queries_select_total" in body
    # And the histogram surfaces as a summary with quantile labels.
    assert 'quantile="0.5"' in body


def test_metrics_body_ends_with_newline(client: TestClient) -> None:
    """Prometheus exposition format requires a trailing newline."""
    body = client.get("/_dazzle/metrics").text
    assert body.endswith("\n")


# ---------------------------------------------------------------------------
# Empty / unconfigured collector
# ---------------------------------------------------------------------------


def test_metrics_endpoint_none_collector_returns_empty_document() -> None:
    """A None collector yields an empty Prometheus document — never 500."""
    app = FastAPI()
    app.include_router(create_metrics_routes(None))
    resp = TestClient(app).get("/_dazzle/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == PROMETHEUS_CONTENT_TYPE
    # Empty document is a single comment line — no metric samples, no errors.
    body = resp.text
    assert "collector not configured" in body
    # Must be parseable as Prometheus: starts with `#` (comment), no stray
    # tokens that could trip a scraper.
    assert body.startswith("#")


def test_metrics_endpoint_collector_failure_returns_empty_document() -> None:
    """If snapshot() raises, the endpoint still returns 200 with an empty doc."""

    class _ExplodingCollector:
        def snapshot(self) -> object:
            raise RuntimeError("collector imploded")

    app = FastAPI()
    app.include_router(create_metrics_routes(_ExplodingCollector()))
    resp = TestClient(app).get("/_dazzle/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == PROMETHEUS_CONTENT_TYPE
    assert "collector not configured" in resp.text
