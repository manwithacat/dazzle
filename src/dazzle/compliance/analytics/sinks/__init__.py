"""Server-side analytics sinks (v0.61.0 Phase 5).

A **sink** consumes analytics events from the framework's event bus and
forwards them to an external analytics provider's server-side ingest
endpoint. This runs in addition to (not instead of) the client-side
dataLayer — server-side events are ad-blocker-proof, don't leak PII to
the client, and work on non-JS clients.

The abstraction mirrors the client-side ``ProviderDefinition`` pattern
but targets a different boundary:

    Client side:  framework template → dataLayer → GTM / Plausible / …
    Server side:  event bus → AnalyticsSink.emit() → GA4 MP / Plausible API / …

See ``docs/superpowers/specs/2026-04-24-analytics-privacy-design.md`` §2.5.
"""

from __future__ import annotations

from .base import (
    AnalyticsEvent,
    AnalyticsSink,
    SinkMetrics,
    SinkResult,
    TenantContext,
)
from .ga4 import GA4MeasurementProtocolSink
from .registry import (
    FRAMEWORK_SINKS,
    get_sink_factory,
    list_sink_names,
)

__all__ = [
    "AnalyticsEvent",
    "AnalyticsSink",
    "FRAMEWORK_SINKS",
    "GA4MeasurementProtocolSink",
    "SinkMetrics",
    "SinkResult",
    "TenantContext",
    "get_sink_factory",
    "list_sink_names",
]
