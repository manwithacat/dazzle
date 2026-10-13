"""
Prometheus scrape endpoint — ``GET /_dazzle/metrics``.

The URL is part of the runtime surface (``/_dazzle/*``, same gating as the
other inspection endpoints) so scrapers can be pointed at it. No metrics
collector is wired into the runtime (the PRA-era ``dazzle.http.metrics``
package was removed in flense ship O, ADR-0057), so the endpoint serves an
empty but valid Prometheus document — a single comment line with the
standard content-type — and scrapes succeed with zero series.
"""

# NO `from __future__ import annotations` here — ADR-0014. A stringified
# return annotation on a route endpoint poisons OpenAPI schema generation
# app-wide (#1365).
from fastapi import APIRouter, Response

# Standard Prometheus text exposition format content-type.
# Pinned exactly as the Prometheus project documents it — both the
# version and charset matter for some scrapers.
PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

# Empty-but-valid Prometheus document. A single comment line is the
# canonical "no metrics" response — scrapers accept it without warnings.
_EMPTY_DOCUMENT = "# Dazzle metrics — collector not configured\n"


def _render_metrics() -> Response:
    return Response(content=_EMPTY_DOCUMENT, media_type=PROMETHEUS_CONTENT_TYPE)


def create_metrics_routes() -> APIRouter:
    """Create the ``/_dazzle/metrics`` Prometheus scrape endpoint."""
    router = APIRouter(prefix="/_dazzle", tags=["Metrics"])
    router.add_api_route(
        "/metrics",
        _render_metrics,
        methods=["GET"],
        # #1365: Prometheus scrape plumbing doesn't belong in OpenAPI.
        include_in_schema=False,
        response_class=Response,
    )
    return router
