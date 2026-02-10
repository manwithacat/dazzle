"""Tests for the sitespec review handler."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from dazzle.mcp.server.handlers.sitespec import review_sitespec_handler


def _mock_sitespec(pages: list[dict[str, Any]] | None = None) -> MagicMock:
    """Create a mock SiteSpec."""
    if pages is None:
        pages = [
            {
                "route": "/",
                "title": "Home",
                "sections": [
                    {"type": "hero", "headline": "Welcome"},
                    {"type": "features", "items": [{"title": "Fast"}]},
                    {"type": "cta", "headline": "Get Started"},
                ],
            },
            {
                "route": "/about",
                "title": "About",
                "sections": [
                    {"type": "hero", "headline": "About Us"},
                    {"type": "unknown_type"},
                ],
            },
        ]
    spec = MagicMock()
    spec.model_dump.return_value = {"pages": pages}
    return spec


def _mock_coherence_report(
    issues: list[dict[str, Any]] | None = None,
    score: int = 80,
) -> MagicMock:
    """Create a mock CoherenceReport."""
    report = MagicMock()
    report.score = score
    report.error_count = 0
    report.warning_count = 0

    mock_issues = []
    for issue_data in issues or []:
        issue = MagicMock()
        issue.severity = MagicMock(value=issue_data.get("severity", "warning"))
        issue.message = issue_data.get("message", "")
        issue.location = issue_data.get("location")
        issue.suggestion = issue_data.get("suggestion")
        mock_issues.append(issue)
    report.issues = mock_issues
    return report


class TestReviewSitespecHandler:
    """Test the sitespec review handler."""

    @patch("dazzle.core.site_coherence.validate_site_coherence")
    @patch("dazzle.core.sitespec_loader.load_copy")
    @patch("dazzle.core.sitespec_loader.load_sitespec")
    def test_basic_review(
        self,
        mock_load: Any,
        mock_copy: Any,
        mock_coherence: Any,
        tmp_path: Any,
    ) -> None:
        mock_load.return_value = _mock_sitespec()
        mock_copy.return_value = None
        mock_coherence.return_value = _mock_coherence_report()

        result = review_sitespec_handler(tmp_path, {})
        data = json.loads(result)

        assert data["status"] == "complete"
        assert data["total_sections"] == 5
        # hero(ok), features(ok), cta(ok), hero(ok), unknown(not ok)
        assert data["rendering_sections"] == 4
        assert data["render_percent"] == 80.0

    @patch("dazzle.core.site_coherence.validate_site_coherence")
    @patch("dazzle.core.sitespec_loader.load_copy")
    @patch("dazzle.core.sitespec_loader.load_sitespec")
    def test_detects_missing_renderer(
        self,
        mock_load: Any,
        mock_copy: Any,
        mock_coherence: Any,
        tmp_path: Any,
    ) -> None:
        mock_load.return_value = _mock_sitespec()
        mock_copy.return_value = None
        mock_coherence.return_value = _mock_coherence_report()

        result = review_sitespec_handler(tmp_path, {})
        data = json.loads(result)

        about_page = [p for p in data["pages"] if p["route"] == "/about"][0]
        unknown_sec = [s for s in about_page["sections"] if s["type"] == "unknown_type"][0]
        assert unknown_sec["has_renderer"] is False
        assert unknown_sec["renders"] is False

    @patch("dazzle.core.site_coherence.validate_site_coherence")
    @patch("dazzle.core.sitespec_loader.load_copy")
    @patch("dazzle.core.sitespec_loader.load_sitespec")
    def test_detects_missing_fields(
        self,
        mock_load: Any,
        mock_copy: Any,
        mock_coherence: Any,
        tmp_path: Any,
    ) -> None:
        pages = [
            {
                "route": "/",
                "title": "Home",
                "sections": [
                    {"type": "hero"},  # Missing headline
                    {"type": "features"},  # Missing items
                ],
            }
        ]
        mock_load.return_value = _mock_sitespec(pages)
        mock_copy.return_value = None
        mock_coherence.return_value = _mock_coherence_report()

        result = review_sitespec_handler(tmp_path, {})
        data = json.loads(result)

        assert data["rendering_sections"] == 0
        sections = data["pages"][0]["sections"]
        assert "headline" in sections[0]["missing_fields"]
        assert "items" in sections[1]["missing_fields"]

    @patch("dazzle.core.site_coherence.validate_site_coherence")
    @patch("dazzle.core.sitespec_loader.load_copy")
    @patch("dazzle.core.sitespec_loader.load_sitespec")
    def test_includes_coherence_issues(
        self,
        mock_load: Any,
        mock_copy: Any,
        mock_coherence: Any,
        tmp_path: Any,
    ) -> None:
        mock_load.return_value = _mock_sitespec()
        mock_copy.return_value = None
        mock_coherence.return_value = _mock_coherence_report(
            issues=[
                {
                    "severity": "warning",
                    "message": "Missing CTA on about page",
                    "location": "/about",
                }
            ]
        )

        result = review_sitespec_handler(tmp_path, {})
        data = json.loads(result)

        about_page = [p for p in data["pages"] if p["route"] == "/about"][0]
        assert about_page["issue_count"] == 1
        assert "Missing CTA" in about_page["issues"][0]["message"]

    @patch("dazzle.core.site_coherence.validate_site_coherence")
    @patch("dazzle.core.sitespec_loader.load_copy")
    @patch("dazzle.core.sitespec_loader.load_sitespec")
    def test_markdown_output(
        self,
        mock_load: Any,
        mock_copy: Any,
        mock_coherence: Any,
        tmp_path: Any,
    ) -> None:
        mock_load.return_value = _mock_sitespec()
        mock_copy.return_value = None
        mock_coherence.return_value = _mock_coherence_report()

        result = review_sitespec_handler(tmp_path, {})
        data = json.loads(result)

        md = data["markdown"]
        assert "Site Review" in md
        assert "4/5 sections" in md
        assert "[ok] Welcome" in md
        assert "[!!] unknown_type" in md
        assert "(no renderer)" in md

    @patch("dazzle.core.site_coherence.validate_site_coherence")
    @patch("dazzle.core.sitespec_loader.load_copy")
    @patch("dazzle.core.sitespec_loader.load_sitespec")
    def test_no_pages(
        self,
        mock_load: Any,
        mock_copy: Any,
        mock_coherence: Any,
        tmp_path: Any,
    ) -> None:
        mock_load.return_value = _mock_sitespec(pages=[])
        mock_copy.return_value = None
        mock_coherence.return_value = _mock_coherence_report()

        result = review_sitespec_handler(tmp_path, {})
        data = json.loads(result)

        assert data["total_sections"] == 0
        assert data["render_percent"] == 0

    @patch("dazzle.core.site_coherence.validate_site_coherence")
    @patch("dazzle.core.sitespec_loader.load_copy")
    @patch("dazzle.core.sitespec_loader.load_sitespec")
    def test_all_sections_rendering(
        self,
        mock_load: Any,
        mock_copy: Any,
        mock_coherence: Any,
        tmp_path: Any,
    ) -> None:
        pages = [
            {
                "route": "/",
                "title": "Home",
                "sections": [
                    {"type": "hero", "headline": "Welcome"},
                    {"type": "cta", "headline": "Sign Up"},
                ],
            }
        ]
        mock_load.return_value = _mock_sitespec(pages)
        mock_copy.return_value = None
        mock_coherence.return_value = _mock_coherence_report()

        result = review_sitespec_handler(tmp_path, {})
        data = json.loads(result)

        assert data["rendering_sections"] == 2
        assert data["render_percent"] == 100.0
