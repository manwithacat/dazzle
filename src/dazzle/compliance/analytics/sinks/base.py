"""Sink protocol + shared types (v0.61.0 Phase 5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class TenantContext:
    """Tenant metadata threaded with every emission.

    Sinks that fan out per tenant (multi-tenant SaaS) read
    ``analytics_config`` to pick the right measurement ID / GA4 property.
    Phase 6 will populate this from the Tenant entity; for now it's
    app-wide defaults.

    Attributes:
        tenant_slug: Stable tenant identifier (used as GA4 client_id fallback
            and as ``dz_tenant`` event parameter).
        analytics_config: Per-tenant config map — sink-specific keys like
            ``ga4_measurement_id``, ``plausible_api_host``, etc.
    """

    tenant_slug: str | None = None
    analytics_config: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalyticsEvent:
    """Normalised event handed to sinks.

    Parameters are already PII-filtered before the sink sees them — the
    bus bridge applies ``strip_pii`` at the boundary.

    Attributes:
        name: Event name (e.g. ``dz_transition``, ``order_completed``).
            For dz/v1 events, prefix is ``dz_``; business events have
            their own naming.
        params: Flat dict of primitive values safe to send.
        client_id: Stable ID for the user/device. For logged-in users,
            typically the user ID; for anonymous, a synthetic cookie ID.
            May be None — sinks that require it will synthesise.
        source: Where the event originated — ``"bus"`` for event-bus
            bridge, ``"direct"`` for manual emission from app code.
            Diagnostic only.
        topic: Bus topic the event came from, when sourced from the bus.
            Used for server-side routing logic (e.g. only some sinks
            consume certain topics).
    """

    name: str
    params: dict[str, Any] = field(default_factory=dict)
    client_id: str | None = None
    source: str = "bus"
    topic: str | None = None


@dataclass
class SinkMetrics:
    """Mutable counters a sink updates during operation.

    Read by observability — the framework exports these as gauges/counters
    under ``dz_analytics_sink_*`` names.
    """

    success_total: int = 0
    failure_total: int = 0
    dropped_total: int = 0  # 4xx responses — bad event shape, don't retry
    last_latency_ms: float = 0.0


@dataclass(frozen=True)
class SinkResult:
    """Outcome of one emission — surfaced for logging / tests."""

    ok: bool
    status_code: int | None = None
    error: str | None = None
    latency_ms: float = 0.0


class AnalyticsSink(Protocol):
    """Protocol every server-side sink implements.

    Sinks should be cheap to construct (no network at init) and safe to
    call concurrently from multiple bus consumers. Implementations own
    their own HTTP client lifecycle.
    """

    name: str
    metrics: SinkMetrics

    async def emit(
        self,
        event: AnalyticsEvent,
        tenant: TenantContext | None = None,
    ) -> SinkResult:
        """Forward the event to the provider's ingest endpoint.

        Errors SHOULD NOT propagate — return a ``SinkResult`` with
        ``ok=False`` and record to ``self.metrics``. Callers log the
        result but don't fail the originating business operation.
        """
        ...

    async def close(self) -> None:
        """Release any held HTTP clients. Idempotent."""
        ...
