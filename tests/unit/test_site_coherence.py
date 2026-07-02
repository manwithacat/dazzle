"""Tests for site coherence validation."""

import pytest

from dazzle.core.site_coherence import (
    CoherenceReport,
    Severity,
    detect_placeholders,
    validate_site_coherence,
)


class TestPlaceholderDetection:
    """Tests for placeholder text detection."""

    @pytest.mark.parametrize(
        "text",
        [
            "Lorem ipsum dolor sit amet",
            "Your Tagline Here",
            "TODO: Add real content",
            "Visit us at example.com",
            "Feature 1, Feature 2, Feature 3",
        ],
        ids=[
            "test_detects_lorem_ipsum",
            "test_detects_your_tagline_here",
            "test_detects_todo",
            "test_detects_example_domain",
            "test_detects_generic_features",
        ],
    )
    def test_detects_placeholder(self, text: str) -> None:
        assert len(detect_placeholders(text)) > 0

    def test_ignores_real_content(self) -> None:
        matches = detect_placeholders(
            "FreshMeals delivers chef-quality meal kits to your door every week."
        )
        assert len(matches) == 0


class TestCoherenceReport:
    """Tests for CoherenceReport."""

    def test_empty_report_is_coherent(self) -> None:
        report = CoherenceReport()
        assert report.is_coherent
        assert report.score == 100

    def test_error_makes_incoherent(self) -> None:
        report = CoherenceReport()
        report.add_error("Test", "Something is broken")
        assert not report.is_coherent
        assert report.error_count == 1

    def test_warnings_dont_break_coherence(self) -> None:
        report = CoherenceReport()
        report.add_warning("Test", "Something could be better")
        assert report.is_coherent
        assert report.warning_count == 1
        assert report.score < 100

    def test_score_calculation(self) -> None:
        report = CoherenceReport()
        report.add_error("Test", "Error 1")  # -20
        report.add_warning("Test", "Warning 1")  # -5
        report.add_suggestion("Test", "Suggestion 1")  # -1
        assert report.score == 100 - 20 - 5 - 1

    def test_to_dict(self) -> None:
        report = CoherenceReport()
        report.add_error("Navigation", "Broken link", location="/about")
        report.add_passed("CTAs valid")

        data = report.to_dict()
        assert data["is_coherent"] is False
        assert data["error_count"] == 1
        assert len(data["issues"]) == 1
        assert data["issues"][0]["category"] == "Navigation"
        assert "CTAs valid" in data["checks_passed"]


class TestNavigationValidation:
    """Tests for navigation link validation."""

    def test_valid_navigation(self) -> None:
        sitespec = {
            "pages": [
                {"route": "/", "sections": []},
                {"route": "/about", "sections": []},
            ],
            "layout": {
                "nav": {
                    "public": [
                        {"label": "Home", "href": "/"},
                        {"label": "About", "href": "/about"},
                    ],
                },
            },
            "legal": {},
            "auth_pages": {},
            "integrations": {},
            "brand": {},
        }
        report = validate_site_coherence(sitespec)
        nav_errors = [i for i in report.issues if i.category == "Navigation"]
        assert len(nav_errors) == 0

    def test_broken_navigation_link(self) -> None:
        sitespec = {
            "pages": [{"route": "/", "sections": []}],
            "layout": {
                "nav": {
                    "public": [
                        {"label": "Features", "href": "/features"},  # Doesn't exist
                    ],
                },
            },
            "legal": {},
            "auth_pages": {},
            "integrations": {},
            "brand": {},
        }
        report = validate_site_coherence(sitespec)
        nav_errors = [i for i in report.issues if i.category == "Navigation"]
        assert len(nav_errors) == 1
        assert nav_errors[0].severity == Severity.ERROR

    def test_external_links_are_valid(self) -> None:
        sitespec = {
            "pages": [{"route": "/", "sections": []}],
            "layout": {
                "nav": {
                    "public": [
                        {"label": "Twitter", "href": "https://twitter.com/example"},
                    ],
                },
            },
            "legal": {},
            "auth_pages": {},
            "integrations": {},
            "brand": {},
        }
        report = validate_site_coherence(sitespec)
        nav_errors = [
            i for i in report.issues if i.category == "Navigation" and i.severity == Severity.ERROR
        ]
        assert len(nav_errors) == 0


class TestRequiredPages:
    """Tests for required page validation."""

    def test_missing_landing_page(self) -> None:
        sitespec = {
            "pages": [{"route": "/about", "sections": []}],
            "layout": {"nav": {}},
            "legal": {},
            "auth_pages": {},
            "integrations": {},
            "brand": {},
        }
        report = validate_site_coherence(sitespec)
        page_errors = [
            i for i in report.issues if i.category == "Required Pages" and "/" in i.message
        ]
        assert len(page_errors) > 0

    def test_saas_missing_pricing(self) -> None:
        sitespec = {
            "pages": [{"route": "/", "sections": []}],
            "layout": {"nav": {}},
            "legal": {},
            "auth_pages": {},
            "integrations": {},
            "brand": {},
        }
        report = validate_site_coherence(sitespec, business_context="saas")
        pricing_warnings = [
            i
            for i in report.issues
            if "pricing" in i.message.lower() and "missing" in i.message.lower()
        ]
        assert len(pricing_warnings) > 0


class TestLegalPages:
    """Tests for legal page validation."""

    def test_missing_legal_pages(self) -> None:
        sitespec = {
            "pages": [{"route": "/", "sections": []}],
            "layout": {"nav": {}},
            "legal": {},
            "auth_pages": {},
            "integrations": {},
            "brand": {},
        }
        report = validate_site_coherence(sitespec)
        legal_warnings = [i for i in report.issues if i.category == "Legal"]
        assert len(legal_warnings) >= 2  # Terms and Privacy

    def test_configured_legal_pages(self) -> None:
        sitespec = {
            "pages": [{"route": "/", "sections": []}],
            "layout": {"nav": {}},
            "legal": {
                "terms": {"route": "/terms"},
                "privacy": {"route": "/privacy"},
            },
            "auth_pages": {},
            "integrations": {},
            "brand": {},
        }
        report = validate_site_coherence(sitespec)
        assert "Legal pages configured" in report.checks_passed


class TestPlaceholderValidation:
    """Tests for placeholder content validation."""

    def test_detects_placeholder_in_brand(self) -> None:
        sitespec = {
            "pages": [{"route": "/", "sections": []}],
            "layout": {"nav": {}},
            "legal": {},
            "auth_pages": {},
            "integrations": {},
            "brand": {
                "product_name": "Your App Here",
                "tagline": "Your Tagline Here",
            },
        }
        report = validate_site_coherence(sitespec)
        placeholder_warnings = [i for i in report.issues if i.category == "Placeholders"]
        assert len(placeholder_warnings) > 0

    def test_real_content_passes(self) -> None:
        sitespec = {
            "pages": [
                {
                    "route": "/",
                    "sections": [
                        {
                            "headline": "FreshMeals - Chef Quality at Home",
                            "body": "Delicious meal kits delivered weekly",
                        }
                    ],
                }
            ],
            "layout": {"nav": {}},
            "legal": {},
            "auth_pages": {},
            "integrations": {},
            "brand": {
                "product_name": "FreshMeals",
                "tagline": "Chef-quality meals delivered",
            },
        }
        report = validate_site_coherence(sitespec)
        placeholder_warnings = [i for i in report.issues if i.category == "Placeholders"]
        assert len(placeholder_warnings) == 0


class TestBranding:
    """Tests for branding validation."""

    def test_incomplete_branding(self) -> None:
        sitespec = {
            "pages": [{"route": "/", "sections": []}],
            "layout": {"nav": {}},
            "legal": {},
            "auth_pages": {},
            "integrations": {},
            "brand": {
                "product_name": "My App",  # Default
            },
        }
        report = validate_site_coherence(sitespec)
        brand_warnings = [i for i in report.issues if i.category == "Branding"]
        assert len(brand_warnings) > 0

    def test_complete_branding(self) -> None:
        sitespec = {
            "pages": [{"route": "/", "sections": []}],
            "layout": {"nav": {}},
            "legal": {},
            "auth_pages": {},
            "integrations": {},
            "brand": {
                "product_name": "FreshMeals",
                "tagline": "Chef-quality meals delivered",
                "support_email": "support@freshmeals.com",
                "company_legal_name": "FreshMeals Inc.",
            },
        }
        report = validate_site_coherence(sitespec)
        assert "Branding is complete" in report.checks_passed


class TestFullValidation:
    """Integration tests for full site validation."""

    def test_minimal_coherent_site(self) -> None:
        """A minimal but coherent site should pass."""
        sitespec = {
            "pages": [
                {
                    "route": "/",
                    "sections": [
                        {
                            "type": "hero",
                            "headline": "Welcome to FreshMeals",
                            "primary_cta": {"label": "Get Started", "href": "/signup"},
                        }
                    ],
                },
                {"route": "/about", "sections": [{"headline": "About Us"}]},
            ],
            "layout": {
                "nav": {
                    "public": [
                        {"label": "Home", "href": "/"},
                        {"label": "About", "href": "/about"},
                    ],
                },
                "footer": {
                    "columns": [
                        {
                            "title": "Company",
                            "links": [{"label": "About", "href": "/about"}],
                        }
                    ],
                },
            },
            "legal": {
                "terms": {"route": "/terms"},
                "privacy": {"route": "/privacy"},
            },
            "auth_pages": {
                "login": {"route": "/login", "enabled": True},
                "signup": {"route": "/signup", "enabled": True},
            },
            "integrations": {"app_mount_route": "/app"},
            "brand": {
                "product_name": "FreshMeals",
                "tagline": "Chef-quality meals delivered",
                "support_email": "support@freshmeals.com",
                "company_legal_name": "FreshMeals Inc.",
            },
        }
        report = validate_site_coherence(sitespec)
        assert report.is_coherent
        assert report.score >= 70  # Some suggestions are OK


class TestStaticAssetHrefs1532:
    """#1532: static-asset hrefs (PDF downloads etc.) are not routes.

    The CTA / nav / footer checks were route-only, so a working
    `/static/samples/pack.pdf` CTA was always an ERROR. Asset hrefs now leave
    the route check entirely; `/static/` hrefs get a filesystem probe against
    `<project_root>/static` where MISSING is a SUGGESTION (build-generated
    artifacts are legitimately absent pre-build), never an error.
    """

    @staticmethod
    def _sitespec(cta_href: str) -> dict:
        return {
            "pages": [
                {
                    "route": "/",
                    "sections": [
                        {
                            "primary_cta": {"label": "Sign up", "href": "/signup"},
                            "secondary_cta": {"label": "Download the PDF pack", "href": cta_href},
                        }
                    ],
                }
            ],
            "layout": {
                "nav": {"public": [{"label": "Home", "href": "/"}]},
                "footer": {"columns": [{"links": [{"label": "Pack", "href": cta_href}]}]},
            },
            "legal": {},
            "auth_pages": {},
            "integrations": {},
            "brand": {},
        }

    def _issues(self, report, categories=("CTAs", "Footer", "Navigation")):
        return [i for i in report.issues if i.category in categories]

    def test_static_asset_present_on_disk_is_clean(self, tmp_path) -> None:
        asset = tmp_path / "static" / "samples" / "sample-pack.pdf"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b"%PDF-1.4")
        report = validate_site_coherence(
            self._sitespec("/static/samples/sample-pack.pdf"), project_root=tmp_path
        )
        assert self._issues(report) == []

    def test_static_asset_missing_is_suggestion_not_error(self, tmp_path) -> None:
        (tmp_path / "static").mkdir()
        report = validate_site_coherence(
            self._sitespec("/static/samples/sample-pack.pdf"), project_root=tmp_path
        )
        issues = self._issues(report)
        assert issues, "missing asset should still be surfaced"
        assert all(i.severity == Severity.SUGGESTION for i in issues)
        assert report.error_count == 0

    def test_static_asset_without_project_root_is_skipped(self) -> None:
        # No static root resolvable → nothing to probe, nothing to flag.
        report = validate_site_coherence(self._sitespec("/static/samples/sample-pack.pdf"))
        assert self._issues(report) == []

    def test_extension_href_outside_static_mount_is_not_a_broken_route(self, tmp_path) -> None:
        # Served by a custom mount the checker doesn't model — asset, not route.
        report = validate_site_coherence(
            self._sitespec("/downloads/brochure.pdf"), project_root=tmp_path
        )
        assert self._issues(report) == []

    def test_query_string_and_fragment_are_ignored_for_asset_detection(self, tmp_path) -> None:
        asset = tmp_path / "static" / "pack.pdf"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b"%PDF-1.4")
        report = validate_site_coherence(
            self._sitespec("/static/pack.pdf?v=2#page=3"), project_root=tmp_path
        )
        assert self._issues(report) == []

    def test_traversal_href_cannot_escape_static_root(self, tmp_path) -> None:
        (tmp_path / "static").mkdir()
        (tmp_path / "secret.pdf").write_bytes(b"%PDF-1.4")  # exists OUTSIDE static/
        report = validate_site_coherence(
            self._sitespec("/static/../secret.pdf"), project_root=tmp_path
        )
        issues = self._issues(report)
        # Must not be treated as found (escape) — surfaced as the missing-asset
        # suggestion, and never an error.
        assert issues and all(i.severity == Severity.SUGGESTION for i in issues)
        assert report.error_count == 0

    def test_plain_route_hrefs_still_flag_as_errors(self) -> None:
        # Regression guard: the asset carve-out must not weaken the route check.
        report = validate_site_coherence(self._sitespec("/nonexistent-page"))
        cta_errors = [
            i
            for i in report.issues
            if i.category in ("CTAs", "Footer") and i.severity == Severity.ERROR
        ]
        assert len(cta_errors) == 2  # secondary CTA + footer link
