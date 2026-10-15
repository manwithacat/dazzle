"""Tests for per-tenant analytics resolution (v0.61.0 Phase 6).

Covers:
- TenantAnalyticsConfig default shape
- App-wide resolver derived from AnalyticsSpec
- set/get/clear resolver registry
- resolve_for_request fail-closed behaviour
- CSP origins union per-request (cross-tenant isolation contract)
"""

from __future__ import annotations

from typing import Any

import pytest

from dazzle.compliance.analytics import (
    TenantAnalyticsConfig,
    clear_tenant_analytics_resolvers,
    get_provider_definition,
    get_tenant_analytics_resolver,
    make_app_wide_resolver,
    resolve_for_request,
    set_tenant_analytics_resolver,
)
from dazzle.core.ir import (
    AnalyticsConsentSpec,
    AnalyticsProviderInstance,
    AnalyticsSpec,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Every test starts with a clean resolver registry."""
    clear_tenant_analytics_resolvers()
    yield
    clear_tenant_analytics_resolvers()


class _FakeRequest:
    """Minimal stand-in for Starlette Request.

    Resolvers read arbitrary attributes (hostname, cookies, headers, state).
    """

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# TenantAnalyticsConfig
# ---------------------------------------------------------------------------


class TestTenantAnalyticsConfigDefaults:
    def test_minimal_defaults(self) -> None:
        cfg = TenantAnalyticsConfig()
        assert cfg.tenant_slug is None
        assert cfg.providers == []
        assert cfg.data_residency == "EU"
        assert cfg.consent_override is None
        assert cfg.privacy_page_url == "/privacy"
        assert cfg.cookie_policy_url is None
        assert cfg.extra == {}

    def test_is_frozen(self) -> None:
        import dataclasses

        cfg = TenantAnalyticsConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            cfg.tenant_slug = "evil"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# App-wide resolver
# ---------------------------------------------------------------------------


class TestAppWideResolver:
    def test_none_spec_empty_providers(self) -> None:
        resolver = make_app_wide_resolver(None)
        cfg = resolver(None)
        assert cfg.providers == []
        assert cfg.data_residency == "EU"

    def test_spec_providers_propagated(self) -> None:
        spec = AnalyticsSpec(
            providers=[AnalyticsProviderInstance(name="gtm", params={"id": "GTM-X"})]
        )
        cfg = make_app_wide_resolver(spec)(None)
        assert len(cfg.providers) == 1
        assert cfg.providers[0].name == "gtm"

    def test_dsl_consent_overrides_resolver_default(self) -> None:
        spec = AnalyticsSpec(
            consent=AnalyticsConsentSpec(
                default_jurisdiction="US",
                consent_override="granted",
            ),
        )
        cfg = make_app_wide_resolver(spec, default_residency="EU")(None)
        # DSL wins over function default.
        assert cfg.data_residency == "US"
        assert cfg.consent_override == "granted"

    def test_resolver_is_request_independent(self) -> None:
        """Same resolver, any request → same config."""
        resolver = make_app_wide_resolver(
            AnalyticsSpec(
                providers=[AnalyticsProviderInstance(name="plausible", params={"domain": "x.com"})]
            )
        )
        a = resolver(_FakeRequest(url="/one"))
        b = resolver(_FakeRequest(url="/two"))
        assert a == b


# ---------------------------------------------------------------------------
# Registry + resolve_for_request
# ---------------------------------------------------------------------------


class TestResolverRegistry:
    def test_no_resolver_returns_empty_default(self) -> None:
        cfg = resolve_for_request(_FakeRequest())
        assert cfg.providers == []
        assert cfg.tenant_slug is None

    def test_no_resolver_uses_fallback_if_provided(self) -> None:
        fallback = TenantAnalyticsConfig(
            tenant_slug="fallback",
            data_residency="US",
        )
        cfg = resolve_for_request(_FakeRequest(), fallback=fallback)
        assert cfg.tenant_slug == "fallback"
        assert cfg.data_residency == "US"

    def test_registered_resolver_invoked(self) -> None:
        spec = AnalyticsSpec(
            providers=[AnalyticsProviderInstance(name="gtm", params={"id": "GTM-APP"})]
        )
        set_tenant_analytics_resolver(make_app_wide_resolver(spec))
        cfg = resolve_for_request(_FakeRequest())
        assert len(cfg.providers) == 1
        assert cfg.providers[0].params["id"] == "GTM-APP"

    def test_get_returns_none_when_unregistered(self) -> None:
        assert get_tenant_analytics_resolver() is None

    def test_get_returns_registered(self) -> None:
        r = make_app_wide_resolver(None)
        set_tenant_analytics_resolver(r)
        assert get_tenant_analytics_resolver() is r

    def test_fail_closed_on_exception(self) -> None:
        def bad(_request: Any) -> TenantAnalyticsConfig:
            raise RuntimeError("db down")

        set_tenant_analytics_resolver(bad)
        cfg = resolve_for_request(_FakeRequest())
        # Silent failure — default empty config.
        assert cfg.providers == []

    def test_non_config_return_type_falls_back(self) -> None:
        def broken(_request: Any) -> Any:
            return "not a config"

        set_tenant_analytics_resolver(broken)
        cfg = resolve_for_request(_FakeRequest())
        assert isinstance(cfg, TenantAnalyticsConfig)
        assert cfg.providers == []


# ---------------------------------------------------------------------------
# Per-tenant resolution (cross-tenant isolation contract)
# ---------------------------------------------------------------------------


class TestPerTenantResolution:
    def test_two_tenants_resolve_independently(self) -> None:
        """Core contract: each request resolves its own config, not a cached
        one from the previous tenant."""

        def by_hostname(request: _FakeRequest) -> TenantAnalyticsConfig:
            host = getattr(request, "hostname", "")
            if host == "acme.example.com":
                return TenantAnalyticsConfig(
                    tenant_slug="acme",
                    providers=[AnalyticsProviderInstance(name="gtm", params={"id": "GTM-ACME"})],
                )
            if host == "beta.example.com":
                return TenantAnalyticsConfig(
                    tenant_slug="beta",
                    providers=[
                        AnalyticsProviderInstance(
                            name="plausible", params={"domain": "beta.example.com"}
                        )
                    ],
                )
            # default: no analytics
            return TenantAnalyticsConfig()

        set_tenant_analytics_resolver(by_hostname)

        acme = resolve_for_request(_FakeRequest(hostname="acme.example.com"))
        beta = resolve_for_request(_FakeRequest(hostname="beta.example.com"))
        none = resolve_for_request(_FakeRequest(hostname="unknown.example.com"))

        assert acme.tenant_slug == "acme"
        assert acme.providers[0].params["id"] == "GTM-ACME"
        assert beta.tenant_slug == "beta"
        assert beta.providers[0].name == "plausible"
        assert none.tenant_slug is None and none.providers == []

    def test_tenant_analytics_config_override_fields(self) -> None:
        def resolver(_request: Any) -> TenantAnalyticsConfig:
            return TenantAnalyticsConfig(
                tenant_slug="uk-only",
                data_residency="UK",
                consent_override="denied",
                privacy_page_url="/policies/privacy-uk",
                cookie_policy_url="/policies/cookies-uk",
            )

        set_tenant_analytics_resolver(resolver)
        cfg = resolve_for_request(_FakeRequest())
        assert cfg.data_residency == "UK"
        assert cfg.consent_override == "denied"
        assert cfg.privacy_page_url == "/policies/privacy-uk"


# ---------------------------------------------------------------------------
# Per-tenant CSP header
# ---------------------------------------------------------------------------


class TestPerTenantCSPHeader:
    """The Content-Security-Policy header a request receives carries exactly
    the analytics origins its tenant resolves to — driven through the
    security-headers middleware on a live app."""

    GTM = "googletagmanager.com"
    PLAUSIBLE = "plausible.io"

    @staticmethod
    def _csp(host: str, fallback: list[str]) -> str:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from dazzle.http.runtime.security_middleware import (
            SecurityHeadersConfig,
            create_security_headers_middleware,
        )

        app = FastAPI()
        app.get("/")(lambda: {"ok": True})
        app.add_middleware(
            create_security_headers_middleware(
                SecurityHeadersConfig(enable_csp=True),
                analytics_providers=[get_provider_definition(n) for n in fallback],
            )
        )
        response = TestClient(app, base_url=f"http://{host}").get("/")
        return response.headers["Content-Security-Policy"]

    @staticmethod
    def _by_host(request: Any) -> TenantAnalyticsConfig:
        return {
            "acme.example.com": TenantAnalyticsConfig(
                providers=[AnalyticsProviderInstance(name="gtm", params={"id": "GTM-X"})]
            ),
            "beta.example.com": TenantAnalyticsConfig(
                providers=[AnalyticsProviderInstance(name="plausible", params={"domain": "x"})]
            ),
        }.get(request.url.hostname, TenantAnalyticsConfig())

    @staticmethod
    def _broken(_request: Any) -> TenantAnalyticsConfig:
        raise RuntimeError("boom")

    @staticmethod
    def _unknown_and_gtm(_request: Any) -> TenantAnalyticsConfig:
        return TenantAnalyticsConfig(
            providers=[
                AnalyticsProviderInstance(name="does_not_exist", params={}),
                AnalyticsProviderInstance(name="gtm", params={"id": "G"}),
            ]
        )

    @staticmethod
    def _plausible_only(_request: Any) -> TenantAnalyticsConfig:
        return TenantAnalyticsConfig(
            providers=[AnalyticsProviderInstance(name="plausible", params={"domain": "x.com"})]
        )

    @pytest.mark.parametrize(
        ("resolver", "fallback", "host", "present", "absent"),
        [
            pytest.param(
                None, ["gtm"], "a.test", [GTM], [], id="app-wide-fallback-without-resolver"
            ),
            pytest.param(
                "_plausible_only",
                ["gtm"],
                "a.test",
                [PLAUSIBLE],
                [GTM],
                id="resolver-wins-over-fallback",
            ),
            pytest.param("_by_host", [], "acme.example.com", [GTM], [PLAUSIBLE], id="tenant-acme"),
            pytest.param("_by_host", [], "beta.example.com", [PLAUSIBLE], [GTM], id="tenant-beta"),
            pytest.param("_by_host", [], "unknown.test", [], [GTM, PLAUSIBLE], id="tenant-unknown"),
            pytest.param("_broken", ["gtm"], "a.test", [GTM], [], id="broken-resolver-falls-back"),
            pytest.param(
                "_unknown_and_gtm", [], "a.test", [GTM], [], id="unknown-provider-name-filtered"
            ),
        ],
    )
    def test_csp_carries_the_request_tenants_analytics_origins(
        self, resolver: str | None, fallback: list[str], host: str, present: list, absent: list
    ) -> None:
        if resolver is not None:
            set_tenant_analytics_resolver(getattr(self, resolver))

        csp = self._csp(host, fallback)

        assert [o for o in present if o not in csp] == []
        assert [o for o in absent if o in csp] == []
