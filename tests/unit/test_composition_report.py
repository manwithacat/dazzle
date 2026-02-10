"""Tests for the combined composition report handler."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Report Handler Tests ─────────────────────────────────────────────


class TestReportCompositionHandler:
    """Test the report MCP handler."""

    def _mock_sitespec(self, *, with_pages: bool = True) -> MagicMock:
        """Create a mock sitespec."""
        sitespec = MagicMock()
        if with_pages:
            section = MagicMock()
            section.type = MagicMock(value="hero")
            page = MagicMock()
            page.route = "/"
            page.sections = [section]
            page.page_type = "landing"
            sitespec.pages = [page]
        else:
            sitespec.pages = []
        return sitespec

    @patch("dazzle.core.sitespec_loader.load_sitespec_with_copy")
    @patch("dazzle.core.composition.run_composition_audit")
    @pytest.mark.asyncio
    async def test_dom_only_report(self, mock_audit: Any, mock_load: Any, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import (
            report_composition_handler,
        )

        mock_load.return_value = self._mock_sitespec()
        mock_audit.return_value = {
            "pages": [
                {
                    "route": "/",
                    "score": 95,
                    "violations_count": {"high": 0, "medium": 1, "low": 0},
                }
            ],
            "overall_score": 95,
            "summary": "1 page, 95/100",
            "markdown": "# Composition Audit\n\nScore: 95/100",
        }

        result = await report_composition_handler(tmp_path, {"operation": "report"})
        data = json.loads(result)

        assert data["dom_score"] == 95
        assert data["visual_score"] is None
        assert data["combined_score"] == 95  # DOM-only = DOM score
        assert "DOM 95/100" in data["summary"]
        assert "visual: not run" in data["summary"]

    @patch("dazzle.core.sitespec_loader.load_sitespec_with_copy")
    @pytest.mark.asyncio
    async def test_empty_sitespec(self, mock_load: Any, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import (
            report_composition_handler,
        )

        mock_load.return_value = self._mock_sitespec(with_pages=False)

        result = await report_composition_handler(tmp_path, {"operation": "report"})
        data = json.loads(result)

        assert data["dom_score"] == 100
        assert data["combined_score"] == 100
        assert "No pages" in data["summary"]

    @patch("dazzle.core.sitespec_loader.load_sitespec_with_copy")
    @patch("dazzle.core.composition.run_composition_audit")
    @patch(
        "dazzle.mcp.server.handlers.composition._run_visual_pipeline",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_combined_report_with_visual(
        self,
        mock_visual: Any,
        mock_audit: Any,
        mock_load: Any,
        tmp_path: Any,
    ) -> None:
        from dazzle.mcp.server.handlers.composition import (
            report_composition_handler,
        )

        mock_load.return_value = self._mock_sitespec()
        mock_audit.return_value = {
            "pages": [
                {
                    "route": "/",
                    "score": 90,
                    "violations_count": {"high": 0, "medium": 2, "low": 0},
                }
            ],
            "overall_score": 90,
            "summary": "1 page, 90/100",
            "markdown": "# Composition Audit\n\nScore: 90/100",
        }
        mock_visual.return_value = {
            "visual_score": 80,
            "findings_by_severity": {"high": 1, "medium": 0, "low": 0},
            "tokens_used": 5000,
            "pages": [],
            "summary": "1 page evaluated",
            "markdown": "# Visual Evaluation\n\nScore: 80/100",
        }

        result = await report_composition_handler(
            tmp_path,
            {"operation": "report", "base_url": "http://localhost:3000"},
        )
        data = json.loads(result)

        assert data["dom_score"] == 90
        assert data["visual_score"] == 80
        # Combined = 90*0.4 + 80*0.6 = 36 + 48 = 84
        assert data["combined_score"] == 84
        assert data["tokens_used"] == 5000
        assert data["findings_by_severity"]["high"] == 1
        assert data["findings_by_severity"]["medium"] == 2

    @patch("dazzle.core.sitespec_loader.load_sitespec_with_copy")
    @patch("dazzle.core.composition.run_composition_audit")
    @patch(
        "dazzle.mcp.server.handlers.composition._run_visual_pipeline",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_visual_pipeline_failure_degrades_gracefully(
        self,
        mock_visual: Any,
        mock_audit: Any,
        mock_load: Any,
        tmp_path: Any,
    ) -> None:
        from dazzle.mcp.server.handlers.composition import (
            report_composition_handler,
        )

        mock_load.return_value = self._mock_sitespec()
        mock_audit.return_value = {
            "pages": [
                {
                    "route": "/",
                    "score": 100,
                    "violations_count": {"high": 0, "medium": 0, "low": 0},
                }
            ],
            "overall_score": 100,
            "summary": "1 page, 100/100",
            "markdown": "# Audit\n\n100/100",
        }
        mock_visual.side_effect = ImportError("Playwright not installed")

        result = await report_composition_handler(
            tmp_path,
            {"operation": "report", "base_url": "http://localhost:3000"},
        )
        data = json.loads(result)

        # Falls back to DOM-only
        assert data["dom_score"] == 100
        assert data["visual_score"] is None
        assert data["combined_score"] == 100

    @patch("dazzle.core.sitespec_loader.load_sitespec_with_copy")
    @patch("dazzle.core.composition.run_composition_audit")
    @pytest.mark.asyncio
    async def test_passes_routes_filter(
        self, mock_audit: Any, mock_load: Any, tmp_path: Any
    ) -> None:
        from dazzle.mcp.server.handlers.composition import (
            report_composition_handler,
        )

        mock_load.return_value = self._mock_sitespec()
        mock_audit.return_value = {
            "pages": [],
            "overall_score": 100,
            "summary": "",
            "markdown": "",
        }

        await report_composition_handler(
            tmp_path,
            {"operation": "report", "pages": ["/about"]},
        )

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args
        assert call_kwargs.kwargs.get("routes_filter") == ["/about"] or call_kwargs[1].get(
            "routes_filter"
        ) == ["/about"]


# ── Markdown Report Tests ────────────────────────────────────────────


class TestCombinedMarkdown:
    """Test combined markdown report generation."""

    def test_dom_only_markdown(self) -> None:
        from dazzle.mcp.server.handlers.composition import (
            _build_combined_markdown,
        )

        md = _build_combined_markdown(
            dom_result={
                "markdown": "# Composition Audit\n\nScore: 95/100\n\nAll good.",
            },
            visual_report=None,
            dom_score=95,
            visual_score=None,
            combined_score=95,
        )

        assert "# Composition Report" in md
        assert "Combined Score: 95/100" in md
        assert "DOM Audit: 95/100" in md
        assert "Visual Evaluation: Not Run" in md
        assert "base_url" in md

    def test_combined_markdown(self) -> None:
        from dazzle.mcp.server.handlers.composition import (
            _build_combined_markdown,
        )

        md = _build_combined_markdown(
            dom_result={
                "markdown": "# Composition Audit\n\nDOM details here.",
            },
            visual_report={
                "markdown": "# Visual Evaluation\n\nVisual details here.",
            },
            dom_score=90,
            visual_score=80,
            combined_score=84,
        )

        assert "Combined Score: 84/100" in md
        assert "DOM Audit: 90/100" in md
        assert "Visual Evaluation: 80/100" in md
        assert "DOM details here" in md
        assert "Visual details here" in md

    def test_visual_error_markdown(self) -> None:
        from dazzle.mcp.server.handlers.composition import (
            _build_combined_markdown,
        )

        md = _build_combined_markdown(
            dom_result={"markdown": ""},
            visual_report={"error": "Playwright not installed"},
            dom_score=100,
            visual_score=None,
            combined_score=100,
        )

        assert "Visual Evaluation: Skipped" in md
        assert "Playwright not installed" in md


# ── Score Combination Tests ──────────────────────────────────────────


class TestScoreCombination:
    """Test the score weighting logic."""

    @patch("dazzle.core.sitespec_loader.load_sitespec_with_copy")
    @patch("dazzle.core.composition.run_composition_audit")
    @patch(
        "dazzle.mcp.server.handlers.composition._run_visual_pipeline",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_perfect_scores(
        self,
        mock_visual: Any,
        mock_audit: Any,
        mock_load: Any,
        tmp_path: Any,
    ) -> None:
        from dazzle.mcp.server.handlers.composition import (
            report_composition_handler,
        )

        mock_load.return_value = MagicMock(pages=[MagicMock()])
        mock_audit.return_value = {
            "pages": [{"violations_count": {}}],
            "overall_score": 100,
            "summary": "",
            "markdown": "",
        }
        mock_visual.return_value = {
            "visual_score": 100,
            "findings_by_severity": {"high": 0, "medium": 0, "low": 0},
            "tokens_used": 1000,
            "pages": [],
            "summary": "",
            "markdown": "",
        }

        result = await report_composition_handler(
            tmp_path,
            {"operation": "report", "base_url": "http://localhost:3000"},
        )
        data = json.loads(result)
        assert data["combined_score"] == 100

    @patch("dazzle.core.sitespec_loader.load_sitespec_with_copy")
    @patch("dazzle.core.composition.run_composition_audit")
    @patch(
        "dazzle.mcp.server.handlers.composition._run_visual_pipeline",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_dom_100_visual_0(
        self,
        mock_visual: Any,
        mock_audit: Any,
        mock_load: Any,
        tmp_path: Any,
    ) -> None:
        from dazzle.mcp.server.handlers.composition import (
            report_composition_handler,
        )

        mock_load.return_value = MagicMock(pages=[MagicMock()])
        mock_audit.return_value = {
            "pages": [{"violations_count": {}}],
            "overall_score": 100,
            "summary": "",
            "markdown": "",
        }
        mock_visual.return_value = {
            "visual_score": 0,
            "findings_by_severity": {"high": 5, "medium": 0, "low": 0},
            "tokens_used": 5000,
            "pages": [],
            "summary": "",
            "markdown": "",
        }

        result = await report_composition_handler(
            tmp_path,
            {"operation": "report", "base_url": "http://localhost:3000"},
        )
        data = json.loads(result)
        # 100*0.4 + 0*0.6 = 40
        assert data["combined_score"] == 40


# ── Geometry Audit Integration Tests ────────────────────────────


class TestGeometryInVisualPipeline:
    """Test that geometry audit is wired into _run_visual_pipeline."""

    @patch("dazzle.core.composition_capture.capture_page_sections", new_callable=AsyncMock)
    @patch("dazzle.core.composition_visual.evaluate_captures")
    @patch("dazzle.core.composition_visual.build_visual_report")
    @patch("dazzle.core.composition.run_geometry_audit")
    @pytest.mark.asyncio
    async def test_geometry_audit_called(
        self,
        mock_geo_audit: Any,
        mock_build: Any,
        mock_evaluate: Any,
        mock_capture: Any,
        tmp_path: Any,
    ) -> None:
        from dazzle.mcp.server.handlers.composition import _run_visual_pipeline

        sitespec = MagicMock(pages=[MagicMock()])
        mock_capture.return_value = [MagicMock(sections=[])]
        mock_evaluate.return_value = []
        mock_build.return_value = {
            "visual_score": 90,
            "findings_by_severity": {"high": 0, "medium": 0, "low": 0},
            "tokens_used": 1000,
            "markdown": "",
        }
        mock_geo_audit.return_value = {
            "violations": [],
            "violations_count": {"high": 0, "medium": 0, "low": 0},
            "geometry_score": 100,
        }

        result = await _run_visual_pipeline(
            project_path=tmp_path,
            base_url="http://localhost:3000",
            sitespec=sitespec,
            routes_filter=None,
            viewports=None,
            focus=None,
            token_budget=50000,
        )

        mock_geo_audit.assert_called_once()
        assert "geometry" in result
        assert result["geometry"]["geometry_score"] == 100

    @patch("dazzle.core.composition_capture.capture_page_sections", new_callable=AsyncMock)
    @patch("dazzle.core.composition_visual.evaluate_captures")
    @patch("dazzle.core.composition_visual.build_visual_report")
    @patch("dazzle.core.composition.run_geometry_audit")
    @pytest.mark.asyncio
    async def test_geometry_findings_merged(
        self,
        mock_geo_audit: Any,
        mock_build: Any,
        mock_evaluate: Any,
        mock_capture: Any,
        tmp_path: Any,
    ) -> None:
        from dazzle.mcp.server.handlers.composition import _run_visual_pipeline

        sitespec = MagicMock(pages=[MagicMock()])
        mock_capture.return_value = [MagicMock(sections=[])]
        mock_evaluate.return_value = []
        mock_build.return_value = {
            "visual_score": 85,
            "findings_by_severity": {"high": 1, "medium": 0, "low": 0},
            "tokens_used": 2000,
            "markdown": "",
        }
        mock_geo_audit.return_value = {
            "violations": [{"rule_id": "stacked-media", "severity": "high"}],
            "violations_count": {"high": 1, "medium": 0, "low": 0},
            "geometry_score": 80,
        }

        result = await _run_visual_pipeline(
            project_path=tmp_path,
            base_url="http://localhost:3000",
            sitespec=sitespec,
            routes_filter=None,
            viewports=None,
            focus=None,
            token_budget=50000,
        )

        # Geometry HIGH (1) merged with visual HIGH (1) = 2
        assert result["findings_by_severity"]["high"] == 2

    @patch("dazzle.core.composition_capture.capture_page_sections", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_no_captures_returns_clean_geometry(
        self,
        mock_capture: Any,
        tmp_path: Any,
    ) -> None:
        from dazzle.mcp.server.handlers.composition import _run_visual_pipeline

        sitespec = MagicMock(pages=[MagicMock()])
        mock_capture.return_value = []

        result = await _run_visual_pipeline(
            project_path=tmp_path,
            base_url="http://localhost:3000",
            sitespec=sitespec,
            routes_filter=None,
            viewports=None,
            focus=None,
            token_budget=50000,
        )

        assert result["geometry"]["geometry_score"] == 100
        assert result["geometry"]["violations"] == []
