"""Analytics block IR (v0.61.0 Phase 3).

The DSL `analytics:` block declares which providers an app wants loaded,
per-provider parameters, and (via `consent:` subsection) default consent
behaviour. Minimal shape for Phase 3:

    app my_app "My App":
      analytics:
        providers:
          gtm:
            id: "GTM-XXXXXX"
          plausible:
            domain: "example.com"
        consent:
          default_jurisdiction: EU

Phases 4-5 extend with auto-event configuration (`auto_events:`) and
server-side sinks (`server_side:`). The IR types here carry fields for
those future extensions so the Pydantic schema is forward-compatible.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AnalyticsProviderInstance(BaseModel):
    """One DSL-declared analytics provider with its per-instance parameters.

    `name` matches a key in the framework provider registry
    (``gtm``, ``plausible``, ...). `params` is the dict of required/optional
    provider parameters supplied in the DSL.
    """

    name: str
    params: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)


class AnalyticsConsentSpec(BaseModel):
    """DSL-declared defaults for the consent banner."""

    default_jurisdiction: str | None = None
    consent_override: str | None = None  # "granted" | "denied"

    model_config = ConfigDict(frozen=True)


class AnalyticsServerSideSpec(BaseModel):
    """DSL-declared server-side sink wiring (v0.61.0 Phase 5).

    Example:

        analytics:
          server_side:
            sink: ga4_measurement_protocol
            measurement_id: "G-XXXXXX"
            bus_topics: [audit.*, transition.*, order.completed]

    Attributes:
        sink: Name of a registered AnalyticsSink (see sinks registry).
        measurement_id: Provider-specific default ID (GA4 property, etc.).
            Can be overridden per-tenant in Phase 6.
        bus_topics: Topic globs the sink subscribes to. ``*`` matches one
            path segment; ``**`` matches any remainder. ``audit.*``
            matches ``audit.order``, not ``audit.order.created``.
    """

    sink: str
    measurement_id: str | None = None
    bus_topics: list[str] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)


class AnalyticsSpec(BaseModel):
    """Top-level `analytics:` block declaration."""

    providers: list[AnalyticsProviderInstance] = Field(default_factory=list)
    consent: AnalyticsConsentSpec | None = None
    server_side: AnalyticsServerSideSpec | None = None

    model_config = ConfigDict(frozen=True)
