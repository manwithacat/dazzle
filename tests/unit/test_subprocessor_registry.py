"""Tests for the framework subprocessor registry (v0.61.0)."""

from __future__ import annotations

from dazzle.compliance.analytics import (
    FRAMEWORK_SUBPROCESSORS,
    get_framework_subprocessor,
    list_framework_subprocessors,
    merge_app_subprocessors,
)
from dazzle.core.ir import (
    ConsentCategory,
    LegalBasis,
    SubprocessorSpec,
)


class TestRegistry:
    def test_ships_expected_providers(self) -> None:
        names = {sp.name for sp in FRAMEWORK_SUBPROCESSORS}
        expected = {
            "google_analytics",
            "google_tag_manager",
            "plausible",
            "stripe",
            "twilio",
            "sendgrid",
            "aws_ses",
            "firebase_cloud_messaging",
        }
        assert expected.issubset(names)

    def test_all_entries_are_framework_default(self) -> None:
        for sp in FRAMEWORK_SUBPROCESSORS:
            assert sp.is_framework_default is True

    def test_list_returns_copy(self) -> None:
        a = list_framework_subprocessors()
        b = list_framework_subprocessors()
        assert a == b
        assert a is not b  # copies, not aliases

    def test_get_by_name_known(self) -> None:
        sp = get_framework_subprocessor("plausible")
        assert sp is not None
        assert sp.label == "Plausible Analytics"
        assert sp.jurisdiction == "EU"
        assert sp.cookies == []  # plausible is cookieless

    def test_get_by_name_unknown(self) -> None:
        assert get_framework_subprocessor("no-such-provider") is None

    def test_every_framework_has_dpa_url(self) -> None:
        """Registered subprocessors must link to a DPA — compliance requirement."""
        for sp in FRAMEWORK_SUBPROCESSORS:
            assert sp.dpa_url, f"{sp.name} missing dpa_url"

    def test_us_subprocessors_have_scc_url(self) -> None:
        """US-handled subprocessors must link to SCCs for EU→US transfers."""
        for sp in FRAMEWORK_SUBPROCESSORS:
            if sp.jurisdiction == "US":
                assert sp.scc_url, f"{sp.name} jurisdiction=US but no scc_url"


class TestMerge:
    def _app_ga(self) -> SubprocessorSpec:
        return SubprocessorSpec(
            name="google_analytics",
            label="Our Custom GA",
            handler="ACME Corp",
            jurisdiction="US",
            retention="3 months",
            legal_basis=LegalBasis.CONSENT,
            consent_category=ConsentCategory.ANALYTICS,
        )

    def test_empty_app_returns_all_defaults(self) -> None:
        merged = merge_app_subprocessors([])
        assert len(merged) == len(FRAMEWORK_SUBPROCESSORS)
        assert {sp.name for sp in merged} == {sp.name for sp in FRAMEWORK_SUBPROCESSORS}

    def test_app_overrides_framework(self) -> None:
        app_ga = self._app_ga()
        merged = merge_app_subprocessors([app_ga])
        ga_entries = [sp for sp in merged if sp.name == "google_analytics"]
        # Exactly one entry; it's the app version.
        assert len(ga_entries) == 1
        assert ga_entries[0].handler == "ACME Corp"
        assert ga_entries[0].is_framework_default is False

    def test_override_does_not_duplicate(self) -> None:
        merged = merge_app_subprocessors([self._app_ga()])
        # Total count unchanged — override replaces, doesn't append.
        assert len(merged) == len(FRAMEWORK_SUBPROCESSORS)

    def test_new_app_subprocessor_appended(self) -> None:
        """App-only subprocessor (no framework default) appears in the merged list."""
        new_sp = SubprocessorSpec(
            name="custom_crm",
            label="Custom CRM",
            handler="Example Co",
            jurisdiction="UK",
            retention="5 years",
            legal_basis=LegalBasis.CONTRACT,
            consent_category=ConsentCategory.FUNCTIONAL,
        )
        merged = merge_app_subprocessors([new_sp])
        names = {sp.name for sp in merged}
        assert "custom_crm" in names
        assert len(merged) == len(FRAMEWORK_SUBPROCESSORS) + 1

    def test_order_app_first(self) -> None:
        """App-declared entries come first in the merged list (declaration order)."""
        merged = merge_app_subprocessors([self._app_ga()])
        assert merged[0].name == "google_analytics"
        assert merged[0].is_framework_default is False
