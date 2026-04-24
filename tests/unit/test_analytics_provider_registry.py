"""Tests for the analytics provider registry (v0.61.0 Phase 3)."""

from __future__ import annotations

from dazzle.compliance.analytics import (
    FRAMEWORK_PROVIDERS,
    ProviderCSPRequirements,
    get_provider_definition,
    list_provider_definitions,
)
from dazzle.core.ir import ConsentCategory


class TestProviderDefinitions:
    def test_registry_ships_gtm_and_plausible(self) -> None:
        names = {p.name for p in FRAMEWORK_PROVIDERS}
        assert "gtm" in names
        assert "plausible" in names

    def test_get_known_provider(self) -> None:
        gtm = get_provider_definition("gtm")
        assert gtm is not None
        assert gtm.label == "Google Tag Manager"
        assert gtm.consent_category is ConsentCategory.ANALYTICS
        assert "id" in gtm.required_params

    def test_get_unknown_returns_none(self) -> None:
        assert get_provider_definition("no-such") is None

    def test_list_returns_copy(self) -> None:
        a = list_provider_definitions()
        b = list_provider_definitions()
        assert a == b
        assert a is not b

    def test_gtm_links_to_subprocessor(self) -> None:
        gtm = get_provider_definition("gtm")
        assert gtm is not None
        assert gtm.linked_subprocessor_name == "google_tag_manager"

    def test_plausible_is_cookieless(self) -> None:
        plausible = get_provider_definition("plausible")
        assert plausible is not None
        # Plausible's CSP requirements don't include cookie-storage origins.
        # It's a single script from plausible.io; nothing else.
        assert plausible.csp.script_src == ("https://plausible.io",)

    def test_gtm_needs_unsafe_inline(self) -> None:
        gtm = get_provider_definition("gtm")
        assert gtm is not None
        # GTM's bootstrap snippet is inline, so 'unsafe-inline' is required
        # on script-src. If we ever switch to nonce-based CSP, this test
        # will catch the regression.
        assert "'unsafe-inline'" in gtm.csp.script_src


class TestCSPRequirementsShape:
    def test_default_fields_empty_tuples(self) -> None:
        req = ProviderCSPRequirements()
        assert req.script_src == ()
        assert req.connect_src == ()
        assert req.img_src == ()

    def test_is_frozen(self) -> None:
        import dataclasses

        import pytest

        req = ProviderCSPRequirements(script_src=("https://x.com",))
        with pytest.raises(dataclasses.FrozenInstanceError):
            req.script_src = ("https://y.com",)  # type: ignore[misc]


class TestProviderRequiredParams:
    def test_gtm_requires_id(self) -> None:
        gtm = get_provider_definition("gtm")
        assert gtm is not None
        assert "id" in gtm.required_params

    def test_plausible_requires_domain(self) -> None:
        plausible = get_provider_definition("plausible")
        assert plausible is not None
        assert "domain" in plausible.required_params

    def test_plausible_has_optional_script_origin(self) -> None:
        plausible = get_provider_definition("plausible")
        assert plausible is not None
        assert "script_origin" in plausible.optional_params
