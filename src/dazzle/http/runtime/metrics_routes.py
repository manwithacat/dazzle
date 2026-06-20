"""
Prometheus scrape endpoint — ``GET /_dazzle/metrics``.

Exposes the runtime's :class:`SystemMetricsCollector` snapshot in the
Prometheus text exposition format (content-type
``text/plain; version=0.0.4; charset=utf-8``).

This is the *pull* side of metrics observability (slice 1 of #1192).
A future slice will add an OTLP push exporter alongside it; the two
are independent and additive.

Sibling of :mod:`dazzle.http.runtime.event_explorer` and
:mod:`dazzle.http.runtime.job_explorer` — same factory shape, same
``/_dazzle/*`` prefix, same auth/gating as the existing inspection
endpoints.

When the collector is not wired (``None``) — for instance, in test apps
or when telemetry is disabled — the endpoint returns an empty but valid
Prometheus document (a single comment line, status 200) rather than a
500. Scrape tooling will read the empty document cleanly.
"""

# NO `from __future__ import annotations` here — ADR-0014. This module
# registers a functools.partial endpoint via add_api_route; a partial has no
# __globals__, so stringified annotations stay ForwardRef('Response') and
# poison OpenAPI schema generation app-wide (#1365).
import logging
from functools import partial
from typing import Any

from fastapi import APIRouter, Response

logger = logging.getLogger(__name__)


# Standard Prometheus text exposition format content-type.
# Pinned exactly as the Prometheus project documents it — both the
# version and charset matter for some scrapers.
PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

# Empty-but-valid Prometheus document returned when the collector is
# not wired. A single comment line is the canonical "no metrics"
# response — scrapers accept it without warnings.
_EMPTY_DOCUMENT = "# Dazzle metrics — collector not configured\n"


def _render_metrics(collector: Any | None) -> Response:
    """
    Render the current metrics snapshot as a Prometheus text response.

    When ``collector`` is ``None`` (telemetry off / not wired), returns
    the empty document rather than 500ing the scrape.
    """
    if collector is None:
        return Response(content=_EMPTY_DOCUMENT, media_type=PROMETHEUS_CONTENT_TYPE)

    try:
        snapshot = collector.snapshot()
        body = snapshot.to_prometheus()
    except Exception:
        # Never 500 a scrape — log + return the empty document so
        # Prometheus keeps polling and the operator notices via the
        # missing series (not the failing target).
        logger.warning("Failed to render Prometheus snapshot", exc_info=True)
        return Response(content=_EMPTY_DOCUMENT, media_type=PROMETHEUS_CONTENT_TYPE)

    # snapshot.to_prometheus() does not append a trailing newline.
    # The Prometheus exposition format requires one — append it here.
    if not body.endswith("\n"):
        body += "\n"
    return Response(content=body, media_type=PROMETHEUS_CONTENT_TYPE)


def create_metrics_routes(collector: Any | None) -> APIRouter:
    """
    Create the ``/_dazzle/metrics`` Prometheus scrape endpoint.

    Args:
        collector: A :class:`SystemMetricsCollector` (or any object
            exposing ``.snapshot().to_prometheus() -> str``). May be
            ``None`` — in which case the endpoint serves the empty
            document.

    Returns:
        APIRouter with the single ``GET /_dazzle/metrics`` route.
    """
    router = APIRouter(prefix="/_dazzle", tags=["Metrics"])
    router.add_api_route(
        "/metrics",
        partial(_render_metrics, collector),
        methods=["GET"],
        # #1365: Prometheus scrape plumbing doesn't belong in OpenAPI, and
        # an explicit response_class spares FastAPI from introspecting the
        # partial's (unresolvable) annotations.
        include_in_schema=False,
        response_class=Response,
    )
    return router
