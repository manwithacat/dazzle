"""GA4 Measurement Protocol sink (v0.61.0 Phase 5).

Forwards events to Google Analytics 4's server-side ingest endpoint.

Endpoint: ``https://www.google-analytics.com/mp/collect``

Authentication: ``api_secret`` query parameter. The secret lives in
``DAZZLE_GA4_API_SECRET`` (environment variable) — never in dazzle.toml
or DSL. A sink constructed without the secret will log a warning on
first emission and return `ok=False`.

Payload shape (GA4 MP v1):

    POST /mp/collect?measurement_id=G-XXXXXX&api_secret=SECRET
    {
        "client_id": "<stable-id>",
        "events": [{"name": "<event_name>", "params": {...}}]
    }

The framework sends one event per request (GA4 accepts up to 25 per
call; batching is a future optimisation, not a correctness concern).

Documented at:
https://developers.google.com/analytics/devguides/collection/protocol/ga4
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import field
from typing import Any

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

from .base import AnalyticsEvent, SinkMetrics, SinkResult, TenantContext

logger = logging.getLogger("dazzle.analytics.sinks.ga4")

_MP_ENDPOINT = "https://www.google-analytics.com/mp/collect"
_API_SECRET_ENV = "DAZZLE_GA4_API_SECRET"

# Retry strategy for transient failures (5xx + network). 4xx responses
# indicate bad event shape — don't retry those.
_MAX_RETRIES = 3
_BACKOFF_SECONDS = (0.5, 1.5, 3.0)


class GA4MeasurementProtocolSink:
    """Server-side GA4 sink.

    Constructed by the registry with a per-provider ``measurement_id``
    sourced from the DSL (``analytics.providers.gtm.id`` is the GTM
    container ID, not the GA4 measurement ID — these are different).
    Per-tenant measurement IDs override the default via
    ``tenant.analytics_config["ga4_measurement_id"]`` in Phase 6.

    Attributes:
        name: Stable identifier ``"ga4_measurement_protocol"``.
        default_measurement_id: Fallback property ID when the tenant
            context doesn't supply one.
        metrics: Mutable counters the app exports.
    """

    name: str = "ga4_measurement_protocol"

    def __init__(
        self,
        default_measurement_id: str | None = None,
        *,
        endpoint: str = _MP_ENDPOINT,
        api_secret: str | None = None,
        timeout_seconds: float = 5.0,
        max_retries: int = _MAX_RETRIES,
        backoff_schedule: tuple[float, ...] = _BACKOFF_SECONDS,
    ) -> None:
        self.default_measurement_id = default_measurement_id
        self._endpoint = endpoint
        # API secret can be set at construction (tests) or read lazily from env
        # on first emission (production).
        self._api_secret_override = api_secret
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_schedule = backoff_schedule
        self._client: Any = None
        self.metrics = SinkMetrics()

    @property
    def _api_secret(self) -> str | None:
        if self._api_secret_override is not None:
            return self._api_secret_override
        return os.environ.get(_API_SECRET_ENV)

    def _ensure_client(self) -> Any:
        if self._client is None:
            if not _HTTPX_AVAILABLE:
                raise RuntimeError(
                    "httpx is required for the GA4 sink. "
                    "Install via `pip install httpx` (bundled in the "
                    "dazzle-dsl[serve] extra)."
                )
            self._client = httpx.AsyncClient(timeout=self._timeout_seconds)
        return self._client

    async def emit(
        self,
        event: AnalyticsEvent,
        tenant: TenantContext | None = None,
    ) -> SinkResult:
        """POST the event to GA4 MP.

        Missing API secret or measurement ID → ``ok=False``, no HTTP call.
        Network / 5xx → retry per ``backoff_schedule``, give up after
        ``max_retries`` attempts.
        4xx → log + drop; retrying won't help a bad event shape.
        """
        api_secret = self._api_secret
        if not api_secret:
            logger.warning(
                "GA4 sink disabled: env var %s is unset. Event %r will be dropped.",
                _API_SECRET_ENV,
                event.name,
            )
            self.metrics.failure_total += 1
            return SinkResult(
                ok=False,
                error=f"{_API_SECRET_ENV} unset",
            )

        measurement_id = (
            tenant.analytics_config.get("ga4_measurement_id") if tenant else None
        ) or self.default_measurement_id
        if not measurement_id:
            logger.warning(
                "GA4 sink has no measurement_id (tenant or default). Dropping %r.",
                event.name,
            )
            self.metrics.failure_total += 1
            return SinkResult(
                ok=False,
                error="no measurement_id",
            )

        payload = self._build_payload(event, tenant)
        params = {"measurement_id": measurement_id, "api_secret": api_secret}

        start = time.monotonic()
        last_error: str | None = None
        status_code: int | None = None

        client = self._ensure_client()

        for attempt in range(1, self._max_retries + 1):
            try:
                response = await client.post(self._endpoint, params=params, json=payload)
                status_code = response.status_code

                if 200 <= status_code < 300:
                    latency_ms = (time.monotonic() - start) * 1000.0
                    self.metrics.success_total += 1
                    self.metrics.last_latency_ms = latency_ms
                    return SinkResult(ok=True, status_code=status_code, latency_ms=latency_ms)

                if 400 <= status_code < 500:
                    # Bad event shape — retries won't help. Log and drop.
                    body_snippet = response.text[:200] if response.text else ""
                    logger.warning(
                        "GA4 sink dropped event %r: %d %s",
                        event.name,
                        status_code,
                        body_snippet,
                    )
                    self.metrics.dropped_total += 1
                    return SinkResult(
                        ok=False,
                        status_code=status_code,
                        error=f"4xx: {body_snippet}",
                        latency_ms=(time.monotonic() - start) * 1000.0,
                    )

                # 5xx — transient; retry.
                last_error = f"{status_code}"

            except Exception as exc:  # pragma: no cover — network surface
                last_error = str(exc) or type(exc).__name__

            if attempt < self._max_retries:
                await asyncio.sleep(
                    self._backoff_schedule[min(attempt - 1, len(self._backoff_schedule) - 1)]
                )

        latency_ms = (time.monotonic() - start) * 1000.0
        self.metrics.failure_total += 1
        self.metrics.last_latency_ms = latency_ms
        logger.error(
            "GA4 sink gave up after %d attempts for event %r: %s",
            self._max_retries,
            event.name,
            last_error,
        )
        return SinkResult(
            ok=False,
            status_code=status_code,
            error=last_error,
            latency_ms=latency_ms,
        )

    def _build_payload(
        self,
        event: AnalyticsEvent,
        tenant: TenantContext | None,
    ) -> dict[str, Any]:
        """Assemble the GA4 MP v1 body for a single event."""
        client_id = event.client_id
        if not client_id:
            # GA4 requires a client_id. Synthesise a stable one from tenant.
            tenant_slug = (tenant.tenant_slug if tenant else None) or "anon"
            # GA4 expects <uint>.<uint> style — emulate by hashing tenant into
            # an int and pairing with the session epoch. Good enough for
            # server-side events that already have their own uniqueness
            # guarantees via the bus event_id.
            client_id = f"{abs(hash(tenant_slug)) % 10**10}.{int(time.time())}"

        # GA4 requires params values to be primitives. strip_pii should have
        # handled that upstream, but belt-and-braces here for anything slipping.
        safe_params = {
            k: v for k, v in event.params.items() if isinstance(v, str | int | float | bool)
        }

        return {
            "client_id": client_id,
            "events": [{"name": event.name, "params": safe_params}],
        }

    async def close(self) -> None:
        """Close the underlying httpx client if created."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# Field-reader entries the orphan detector tracks — the framework reads
# these from an external surface during runtime wiring.
_ = field  # silence unused import
