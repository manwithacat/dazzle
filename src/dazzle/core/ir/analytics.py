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


class AnalyticsSpec(BaseModel):
    """Top-level `analytics:` block declaration."""

    providers: list[AnalyticsProviderInstance] = Field(default_factory=list)
    consent: AnalyticsConsentSpec | None = None

    model_config = ConfigDict(frozen=True)
