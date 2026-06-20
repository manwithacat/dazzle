"""Tests for provider rendering + CSP injection (v0.61.0 Phase 3)."""

from __future__ import annotations

import pytest

from dazzle.compliance.analytics import (
    resolve_active_providers,
)
from dazzle.compliance.analytics.consent import (
    ConsentDefaults,
    build_decided_state,
)
from dazzle.core.ir import (
    AnalyticsProviderInstance,
    AnalyticsSpec,
)
from dazzle.http.runtime.security_middleware import _build_csp_header


def _spec(*providers: tuple[str, dict[str, str]]) -> AnalyticsSpec:
    return AnalyticsSpec(
        providers=[AnalyticsProviderInstance(name=n, params=p) for n, p in providers]
    )


class TestResolveActiveProviders:
    @pytest.mark.parametrize(
        "spec_factory",
        [
            lambda: None,
            lambda: AnalyticsSpec(),
            lambda: _spec(("no_such_provider", {"id": "x"})),
            lambda: _spec(("plausible", {})),  # missing required `domain`
        ],
        ids=[
            "test_none_analytics_returns_empty",
            "test_no_providers_returns_empty",
            "test_unknown_provider_skipped",
            "test_missing_required_params_skipped",
        ],
    )
    def test_returns_empty(self, spec_factory) -> None:
        state = build_decided_state(
            analytics=True, advertising=True, personalization=True, functional=True
        )
        assert resolve_active_providers(spec_factory(), state) == []

    def test_plausible_gated_on_analytics_consent(self) -> None:
        spec = _spec(("plausible", {"domain": "example.com"}))

        denied = build_decided_state(
            analytics=False, advertising=False, personalization=False, functional=True
        )
        assert resolve_active_providers(spec, denied) == []

        granted = build_decided_state(
            analytics=True, advertising=False, personalization=False, functional=True
        )
        active = resolve_active_providers(spec, granted)
        assert len(active) == 1
        assert active[0]["name"] == "plausible"

    def test_gtm_always_loads_for_consent_mode_v2(self) -> None:
        """GTM bootstraps even when analytics is denied so Consent Mode v2
        can signal the container when the user later grants."""
        spec = _spec(("gtm", {"id": "GTM-X"}))

        denied = build_decided_state(
            analytics=False, advertising=False, personalization=False, functional=True
        )
        active = resolve_active_providers(spec, denied)
        assert len(active) == 1
        assert active[0]["name"] == "gtm"
        assert active[0]["params"]["id"] == "GTM-X"

    def test_undecided_consent_state(self) -> None:
        """EU default-undecided state: analytics denied → no plausible, but
        GTM still loads (Consent Mode v2 bootstrap)."""
        spec = _spec(
            ("gtm", {"id": "GTM-X"}),
            ("plausible", {"domain": "example.com"}),
        )
        eu_defaults = ConsentDefaults.for_jurisdiction("EU")
        undecided = eu_defaults.to_undecided_state()
        active = resolve_active_providers(spec, undecided)
        names = {p["name"] for p in active}
        assert names == {"gtm"}

    def test_dict_consent_input_supported(self) -> None:
        """render supports dict-shaped consent from template context."""
        spec = _spec(("plausible", {"domain": "example.com"}))
        active = resolve_active_providers(
            spec,
            {
                "analytics": True,
                "advertising": False,
                "personalization": False,
                "functional": True,
            },
        )
        assert len(active) == 1
        assert active[0]["name"] == "plausible"

    def test_render_entry_contains_renderers(self) -> None:
        # Post-#1044: head_template/noscript_template (Jinja paths) are
        # replaced by head_renderer/noscript_renderer Python callables.
        from dazzle.compliance.analytics.provider_html import (
            render_gtm_head,
            render_gtm_noscript,
        )

        spec = _spec(("gtm", {"id": "GTM-X"}))
        state = build_decided_state(
            analytics=True, advertising=True, personalization=True, functional=True
        )
        active = resolve_active_providers(spec, state)
        entry = active[0]
        assert entry["head_renderer"] is render_gtm_head
        assert entry["noscript_renderer"] is render_gtm_noscript
        assert entry["body_renderer"] is None


class TestCSPHeaderInjection:
    def test_baseline_csp_unchanged(self) -> None:
        """No providers → same CSP as before Phase 3."""
        csp = _build_csp_header(None)
        assert "'self'" in csp
        assert "https://cdn.jsdelivr.net" in csp
        # GTM/Plausible origins must NOT appear without providers declared.
        assert "googletagmanager" not in csp
        assert "plausible" not in csp

    def test_gtm_origins_added(self) -> None:
        from dazzle.compliance.analytics import get_provider_definition

        gtm = get_provider_definition("gtm")
        csp = _build_csp_header(None, providers=[gtm])
        assert "https://www.googletagmanager.com" in csp
        assert "https://www.google-analytics.com" in csp

    def test_plausible_origins_added(self) -> None:
        from dazzle.compliance.analytics import get_provider_definition

        plausible = get_provider_definition("plausible")
        csp = _build_csp_header(None, providers=[plausible])
        assert "https://plausible.io" in csp

    def test_multiple_providers_union_origins(self) -> None:
        from dazzle.compliance.analytics import list_provider_definitions

        csp = _build_csp_header(None, providers=list_provider_definitions())
        assert "https://www.googletagmanager.com" in csp
        assert "https://plausible.io" in csp

    def test_custom_directives_override(self) -> None:
        """Explicit directives argument still wins over provider union."""
        from dazzle.compliance.analytics import get_provider_definition

        gtm = get_provider_definition("gtm")
        csp = _build_csp_header(
            {"script-src": "'self'"},
            providers=[gtm],
        )
        # Custom override: script-src is plain 'self', no GTM origin.
        assert "script-src 'self'" in csp
        assert "https://www.googletagmanager.com" not in csp.split("script-src")[1].split(";")[0]
