"""Tests for the framework subprocessor registry (v0.61.0)."""

from __future__ import annotations

from dazzle.compliance.analytics import (
    FRAMEWORK_SUBPROCESSORS,
    get_framework_subprocessor,
    list_framework_subprocessors,
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

    def test_framework_defaults_are_reference_only(self) -> None:
        """#1542 (strict declared-only): the framework catalogue exists as
        a REFERENCE for the audit command — it is never merged into an
        app's compliance artefacts. The old merge helper is deleted."""
        import dazzle.compliance.analytics as analytics

        assert not hasattr(analytics, "merge_app_subprocessors")
        assert len(FRAMEWORK_SUBPROCESSORS) > 0  # the reference catalogue remains

    def test_declared_register_is_authoritative(self) -> None:
        """#1542: the privacy generator consumes appspec.subprocessors
        verbatim — a declared GA entry appears exactly once (the app's
        version), and NO undeclared framework default rides along."""
        from types import SimpleNamespace

        from dazzle.compliance.analytics.privacy_page import (
            generate_privacy_page_markdown,
        )

        spec = SimpleNamespace(
            name="t",
            title="T",
            subprocessors=[self._app_ga()],
            domain=SimpleNamespace(entities=[]),
            analytics=None,
        )
        md = generate_privacy_page_markdown(spec).privacy_policy
        assert "ACME Corp" in md
        assert "Twilio" not in md  # undeclared framework default stays out

    def test_zero_declarations_yield_empty_register(self) -> None:
        """#1542 strict mode: an app with no `subprocessor` declarations
        asserts NO vendors — a compliance document never carries a
        default superset."""
        from types import SimpleNamespace

        from dazzle.compliance.analytics.privacy_page import (
            generate_privacy_page_markdown,
        )

        spec = SimpleNamespace(
            name="t",
            title="T",
            subprocessors=[],
            domain=SimpleNamespace(entities=[]),
            analytics=None,
        )
        md = generate_privacy_page_markdown(spec).privacy_policy
        for default in FRAMEWORK_SUBPROCESSORS:
            assert default.handler not in md
