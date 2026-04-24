"""Per-tenant analytics resolution (v0.61.0 Phase 6).

Multi-tenant Dazzle apps can route analytics per tenant — tenant A fires
to GTM-ABC, tenant B to GTM-DEF, tenant C has analytics disabled. The
framework provides a resolver protocol; app code implements tenant
lookup against whatever shape the tenant entity takes.

Default resolver → single-tenant mode: every request receives the
app-wide config declared in DSL / TOML. Apps that need per-tenant
routing replace the default via ``set_tenant_analytics_resolver()`` at
startup.

The resolver is a **request → TenantAnalyticsConfig** callable. It runs
on every analytics-touching request (site page render + /dz/consent
endpoints + CSP middleware). Implementations should be fast — cache
tenant lookups behind their own in-process / Redis layer.

## Cross-tenant isolation contract

Two requests arriving on the same server for different tenants MUST
resolve to independent configs. Framework code never caches the last
resolved config across requests; resolvers are responsible for ensuring
a slow call is cached *per tenant*, not per process.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from dazzle.core.ir import AnalyticsProviderInstance, AnalyticsSpec

logger = logging.getLogger("dazzle.analytics.tenant")


@dataclass(frozen=True)
class TenantAnalyticsConfig:
    """Fully-resolved analytics config for one tenant + request.

    Fields are read at render time to decide:
      - which provider scripts to inject (``providers``)
      - which CSP origins to allow (derived from providers)
      - what consent defaults to present (``data_residency``, ``consent_override``)
      - what privacy-page / cookie-policy URL the consent banner links to
      - ``tenant_slug`` populates ``data-dz-tenant`` on <body>

    An empty providers list means "no analytics on this tenant's pages"
    — the CSP stays strict and no scripts load. Useful for freemium
    tiers where only paying tenants get telemetry.

    Attributes:
        tenant_slug: Stable per-tenant identifier. None → single-tenant mode.
        providers: Provider instances to activate for this request.
        data_residency: ISO country / region code driving consent defaults.
            EU/UK/EEA → denied, else granted. See ConsentDefaults.
        consent_override: Hard override for default — ``"granted"`` or ``"denied"``.
        privacy_page_url: Override for banner's Privacy-notice link.
        cookie_policy_url: Override for banner's Cookie-policy link.
        ga4_api_secret_env: Optional env-var name to read the GA4 API
            secret from for this tenant. None → use the framework default
            (``DAZZLE_GA4_API_SECRET``).
        extra: Escape hatch for custom resolver → app code integration.
    """

    tenant_slug: str | None = None
    providers: list[AnalyticsProviderInstance] = field(default_factory=list)
    data_residency: str = "EU"
    consent_override: str | None = None
    privacy_page_url: str = "/privacy"
    cookie_policy_url: str | None = None
    ga4_api_secret_env: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class TenantAnalyticsResolver(Protocol):
    """Callable that produces per-request TenantAnalyticsConfig.

    Signature: ``(request) -> TenantAnalyticsConfig``.

    The ``request`` parameter is Request-like — duck-typed to avoid a hard
    FastAPI dependency in the compliance package. Resolvers typically
    read:

      - ``request.url.hostname`` (subdomain-based tenancy)
      - ``request.state.tenant`` (middleware-populated)
      - ``request.cookies.get(...)`` (cookie-based)
      - ``request.headers.get(...)`` (header-based)

    Raising from the resolver is treated as "no analytics for this
    request" (fail-closed) — the framework logs and proceeds with the
    strict default CSP.
    """

    def __call__(self, request: Any) -> TenantAnalyticsConfig: ...


# ---------------------------------------------------------------------------
# Default / app-wide resolver (single-tenant fallback)
# ---------------------------------------------------------------------------


def make_app_wide_resolver(
    spec: AnalyticsSpec | None,
    *,
    default_residency: str = "EU",
    default_override: str | None = None,
    privacy_page_url: str = "/privacy",
    cookie_policy_url: str | None = None,
) -> TenantAnalyticsResolver:
    """Return a resolver that always produces the app-wide config.

    Used when no per-tenant customisation is needed. The returned
    resolver ignores the request and returns the single cached
    ``TenantAnalyticsConfig`` derived from the DSL's ``analytics:`` block
    and app-level defaults.

    Most apps use this — the TOML + DSL already describe their full
    analytics config. Per-tenant resolution is an opt-in for real
    multi-tenant SaaS.
    """
    providers = list(spec.providers) if spec is not None else []

    # DSL consent block overrides the app-level defaults.
    if spec is not None and spec.consent is not None:
        if spec.consent.default_jurisdiction:
            default_residency = spec.consent.default_jurisdiction
        if spec.consent.consent_override:
            default_override = spec.consent.consent_override

    cached = TenantAnalyticsConfig(
        tenant_slug=None,  # single-tenant mode: body tag omits data-dz-tenant
        providers=providers,
        data_residency=default_residency,
        consent_override=default_override,
        privacy_page_url=privacy_page_url,
        cookie_policy_url=cookie_policy_url,
    )

    def resolver(request: Any) -> TenantAnalyticsConfig:
        return cached

    return resolver


# ---------------------------------------------------------------------------
# Process-wide resolver registry
# ---------------------------------------------------------------------------

_resolver_registry: dict[str, TenantAnalyticsResolver] = {}
_DEFAULT_KEY = "__default__"


def set_tenant_analytics_resolver(
    resolver: TenantAnalyticsResolver,
    *,
    app_key: str = _DEFAULT_KEY,
) -> None:
    """Register a resolver for the current (or a named) Dazzle app.

    Multi-app servers (rare) can pass distinct ``app_key`` values to
    keep per-app resolvers separate. Single-app processes (the common
    case) use the default key and forget about it.

    Call this during application startup — typically inside a
    ``on_startup`` hook or the app factory's post-build phase.
    """
    _resolver_registry[app_key] = resolver
    logger.info(
        "Registered tenant analytics resolver under key %r (name=%s).",
        app_key,
        getattr(resolver, "__name__", type(resolver).__name__),
    )


def get_tenant_analytics_resolver(
    app_key: str = _DEFAULT_KEY,
) -> TenantAnalyticsResolver | None:
    """Return the registered resolver for ``app_key``, or None."""
    return _resolver_registry.get(app_key)


def clear_tenant_analytics_resolvers() -> None:
    """Wipe the registry. Test-only helper — production code never calls this."""
    _resolver_registry.clear()


# ---------------------------------------------------------------------------
# Fail-safe resolution
# ---------------------------------------------------------------------------


def resolve_for_request(
    request: Any,
    *,
    fallback: TenantAnalyticsConfig | None = None,
    app_key: str = _DEFAULT_KEY,
) -> TenantAnalyticsConfig:
    """Return the tenant config for this request.

    Fails closed — if no resolver is registered or the resolver raises,
    returns the ``fallback`` (or a no-analytics default). This is the
    framework's single call-site; everything downstream (CSP builder,
    banner renderer, provider injection) reads from the returned value.
    """
    resolver = get_tenant_analytics_resolver(app_key)
    if resolver is None:
        return fallback or TenantAnalyticsConfig()
    try:
        result = resolver(request)
        if isinstance(result, TenantAnalyticsConfig):
            return result
        logger.warning(
            "tenant_analytics_resolver returned non-TenantAnalyticsConfig "
            "(%s); falling back to no-analytics.",
            type(result).__name__,
        )
        return fallback or TenantAnalyticsConfig()
    except Exception:
        logger.exception(
            "tenant_analytics_resolver raised — falling back to no-analytics for this request."
        )
        return fallback or TenantAnalyticsConfig()
