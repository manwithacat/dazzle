"""Tests for the composition visual evaluation pipeline."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from dazzle.core.composition_capture import CapturedPage, CapturedSection
from dazzle.core.composition_visual import (
    DIMENSION_PREPROCESSING,
    DIMENSIONS,
    MOBILE_ONLY_DIMENSIONS,
    PageVisualResult,
    VisualFinding,
    _build_color_consistency_prompt,
    _build_content_rendering_prompt,
    _build_icon_media_prompt,
    _build_layout_overflow_prompt,
    _build_responsive_fidelity_prompt,
    _build_visual_hierarchy_prompt,
    _parse_findings,
    _score_findings,
    apply_filter,
    build_visual_report,
    evaluate_captures,
    image_to_base64,
)

_has_pillow = importlib.util.find_spec("PIL") is not None

# ── Filter Tests ─────────────────────────────────────────────────────


@pytest.mark.skipif(not _has_pillow, reason="Pillow not installed")
class TestApplyFilter:
    """Test image preprocessing filters."""

    def test_no_filter_returns_original(self, tmp_path: Any) -> None:
        from PIL import Image

        img = Image.new("RGB", (100, 100), color="red")
        src = tmp_path / "test.png"
        img.save(src)

        result = apply_filter(src, None)
        assert result == src

    def test_blur_filter(self, tmp_path: Any) -> None:
        from PIL import Image

        img = Image.new("RGB", (100, 100), color="blue")
        src = tmp_path / "test.png"
        img.save(src)

        result = apply_filter(src, "blur")
        assert result.name == "test-blur.png"
        assert result.exists()

    def test_edge_filter(self, tmp_path: Any) -> None:
        from PIL import Image

        img = Image.new("RGB", (100, 100), color="green")
        src = tmp_path / "test.png"
        img.save(src)

        result = apply_filter(src, "edge")
        assert result.name == "test-edges.png"
        assert result.exists()
        # Edge detection converts to grayscale
        out = Image.open(result)
        assert out.mode == "L"

    def test_monochrome_filter(self, tmp_path: Any) -> None:
        from PIL import Image

        img = Image.new("RGB", (100, 100), color=(200, 200, 200))
        src = tmp_path / "test.png"
        img.save(src)

        result = apply_filter(src, "monochrome")
        assert result.name == "test-mono.png"
        assert result.exists()
        out = Image.open(result)
        assert out.mode == "L"

    def test_quantize_filter(self, tmp_path: Any) -> None:
        from PIL import Image

        img = Image.new("RGB", (100, 100), color="purple")
        src = tmp_path / "test.png"
        img.save(src)

        result = apply_filter(src, "quantize")
        assert result.name == "test-quant.png"
        assert result.exists()

    def test_unknown_filter_returns_original(self, tmp_path: Any) -> None:
        from PIL import Image

        img = Image.new("RGB", (10, 10))
        src = tmp_path / "test.png"
        img.save(src)

        result = apply_filter(src, "nonexistent")
        assert result == src

    def test_without_pillow(self, tmp_path: Any) -> None:
        """Returns original path if Pillow not available."""
        src = tmp_path / "test.png"
        src.write_bytes(b"fake png")

        with patch.dict("sys.modules", {"PIL": None, "PIL.Image": None, "PIL.ImageFilter": None}):
            import importlib

            import dazzle.core.composition_visual as mod

            importlib.reload(mod)
            result = mod.apply_filter(src, "blur")
            assert result == src
            importlib.reload(mod)


class TestImageToBase64:
    """Test base64 encoding of images."""

    def test_encodes_file(self, tmp_path: Any) -> None:
        src = tmp_path / "test.png"
        src.write_bytes(b"\x89PNG\r\n\x1a\n")

        result = image_to_base64(src)
        import base64

        decoded = base64.b64decode(result)
        assert decoded == b"\x89PNG\r\n\x1a\n"


# ── Prompt Builder Tests ─────────────────────────────────────────────


class TestPromptBuilders:
    """Test evaluation dimension prompt builders."""

    def test_content_rendering_prompt(self) -> None:
        prompt = _build_content_rendering_prompt(
            "hero",
            {"headline": "Welcome", "item_count": 3, "media_type": "image"},
        )
        assert "hero" in prompt
        assert "Welcome" in prompt
        assert "3 items" in prompt
        assert "image media" in prompt
        assert "monochrome" in prompt.lower()

    def test_content_rendering_prompt_minimal(self) -> None:
        prompt = _build_content_rendering_prompt("features", {})
        assert "features" in prompt
        assert "findings" in prompt

    def test_icon_media_prompt(self) -> None:
        prompt = _build_icon_media_prompt(
            "features",
            {"icon_count": 6, "icon_type": "Lucide"},
        )
        assert "features" in prompt
        assert "6" in prompt
        assert "Lucide" in prompt
        assert "Blank squares" in prompt

    def test_color_consistency_prompt(self) -> None:
        prompt = _build_color_consistency_prompt(
            "cta",
            {"brand_hue": "230", "brand_description": "navy blue"},
        )
        assert "cta" in prompt
        assert "navy blue" in prompt
        assert "230" in prompt
        assert "quantized" in prompt.lower()

    def test_color_consistency_prompt_no_hue(self) -> None:
        prompt = _build_color_consistency_prompt("cta", {})
        assert "brand color" in prompt

    def test_layout_overflow_prompt(self) -> None:
        prompt = _build_layout_overflow_prompt(
            "pricing",
            {"columns": 3, "item_count": 4, "item_type": "pricing tiers"},
        )
        assert "pricing" in prompt
        assert "3-column" in prompt
        assert "4 pricing tiers" in prompt

    def test_layout_overflow_prompt_no_columns(self) -> None:
        prompt = _build_layout_overflow_prompt("features", {})
        assert "features" in prompt
        assert "overflow" in prompt.lower()

    def test_visual_hierarchy_prompt(self) -> None:
        prompt = _build_visual_hierarchy_prompt(
            "hero",
            {"weights": {"h1": 7.30, "subhead": 2.39}},
        )
        assert "hero" in prompt
        assert "h1: 7.3" in prompt
        assert "subhead: 2.39" in prompt
        assert "blur" in prompt.lower()

    def test_visual_hierarchy_prompt_no_weights(self) -> None:
        prompt = _build_visual_hierarchy_prompt("hero", {})
        assert "no weight data" in prompt

    def test_responsive_fidelity_prompt(self) -> None:
        prompt = _build_responsive_fidelity_prompt("hero", {})
        assert "375px" in prompt
        assert "mobile" in prompt
        assert "44px" in prompt


# ── Finding Parser Tests ─────────────────────────────────────────────


class TestParseFindings:
    """Test LLM response parsing."""

    def test_valid_json(self) -> None:
        response = json.dumps(
            {
                "findings": [
                    {
                        "section": "hero",
                        "category": "content_rendering",
                        "severity": "high",
                        "finding": "Headline missing",
                        "evidence": "White block where headline should be",
                        "remediation": "Check markdown content loading",
                    }
                ]
            }
        )
        findings = _parse_findings(response, "hero", "content_rendering")
        assert len(findings) == 1
        assert findings[0].severity == "high"
        assert findings[0].finding == "Headline missing"

    def test_empty_findings(self) -> None:
        response = json.dumps({"findings": []})
        findings = _parse_findings(response, "hero", "content_rendering")
        assert findings == []

    def test_markdown_fenced_json(self) -> None:
        response = '```json\n{"findings": [{"section": "hero", "severity": "low", "finding": "Minor issue", "evidence": "Slight misalignment", "remediation": "Adjust CSS"}]}\n```'
        findings = _parse_findings(response, "hero", "visual_hierarchy")
        assert len(findings) == 1
        assert findings[0].severity == "low"

    def test_invalid_json(self) -> None:
        findings = _parse_findings("not json at all", "hero", "content_rendering")
        assert findings == []

    def test_missing_fields_use_defaults(self) -> None:
        response = json.dumps({"findings": [{"finding": "Something wrong"}]})
        findings = _parse_findings(response, "features", "icon_media")
        assert len(findings) == 1
        assert findings[0].section == "features"
        assert findings[0].dimension == "icon_media"
        assert findings[0].severity == "medium"  # default


# ── Scoring Tests ────────────────────────────────────────────────────


class TestScoring:
    """Test visual finding scoring."""

    def test_no_findings_perfect_score(self) -> None:
        assert _score_findings([]) == 100

    def test_high_severity_deduction(self) -> None:
        findings = [VisualFinding("hero", "content", "content", "high", "Missing", "", "")]
        assert _score_findings(findings) == 80  # 100 - 20

    def test_medium_severity_deduction(self) -> None:
        findings = [VisualFinding("hero", "color", "color", "medium", "Wrong color", "", "")]
        assert _score_findings(findings) == 92  # 100 - 8

    def test_low_severity_deduction(self) -> None:
        findings = [VisualFinding("hero", "layout", "layout", "low", "Minor", "", "")]
        assert _score_findings(findings) == 97  # 100 - 3

    def test_multiple_findings_cumulative(self) -> None:
        findings = [
            VisualFinding("hero", "d", "c", "high", "a", "", ""),
            VisualFinding("hero", "d", "c", "medium", "b", "", ""),
            VisualFinding("hero", "d", "c", "low", "c", "", ""),
        ]
        assert _score_findings(findings) == 69  # 100 - 20 - 8 - 3

    def test_score_floor_at_zero(self) -> None:
        findings = [VisualFinding("s", "d", "c", "high", str(i), "", "") for i in range(10)]
        assert _score_findings(findings) == 0


# ── Report Builder Tests ─────────────────────────────────────────────


class TestBuildVisualReport:
    """Test report generation."""

    def test_empty_results(self) -> None:
        report = build_visual_report([])
        assert report["visual_score"] == 100
        assert report["tokens_used"] == 0
        assert report["findings_by_severity"] == {"high": 0, "medium": 0, "low": 0}

    def test_single_page_with_findings(self) -> None:
        result = PageVisualResult(
            route="/",
            viewport="desktop",
            findings=[
                VisualFinding(
                    "hero",
                    "content",
                    "content_rendering",
                    "high",
                    "Missing headline",
                    "White block",
                    "Load content",
                ),
                VisualFinding(
                    "features",
                    "icon",
                    "icon_media",
                    "medium",
                    "Icons blank",
                    "Placeholder squares",
                    "Init Lucide",
                ),
            ],
            visual_score=72,
            tokens_used=5000,
            dimensions_evaluated=["hero:content_rendering", "features:icon_media"],
        )
        report = build_visual_report([result])
        assert report["visual_score"] == 72
        assert report["findings_by_severity"]["high"] == 1
        assert report["findings_by_severity"]["medium"] == 1
        assert report["tokens_used"] == 5000
        assert len(report["pages"]) == 1

    def test_markdown_report(self) -> None:
        result = PageVisualResult(
            route="/",
            viewport="desktop",
            findings=[
                VisualFinding(
                    "hero",
                    "content",
                    "content_rendering",
                    "high",
                    "Missing headline",
                    "White block",
                    "Load content",
                ),
            ],
            visual_score=80,
            tokens_used=3000,
        )
        report = build_visual_report([result])
        md = report["markdown"]
        assert "# Visual Evaluation Report" in md
        assert "80/100" in md
        assert "[HIGH]" in md
        assert "Missing headline" in md

    def test_summary_text(self) -> None:
        result = PageVisualResult(route="/", viewport="desktop", visual_score=100)
        report = build_visual_report([result])
        assert "1 page(s) evaluated" in report["summary"]
        assert "0 finding(s)" in report["summary"]

    def test_multi_page_average(self) -> None:
        results = [
            PageVisualResult(route="/", viewport="desktop", visual_score=80),
            PageVisualResult(route="/about", viewport="desktop", visual_score=100),
        ]
        report = build_visual_report(results)
        assert report["visual_score"] == 90  # (80+100)//2

    def test_report_includes_skip_diagnostics(self) -> None:
        result = PageVisualResult(
            route="/",
            viewport="desktop",
            visual_score=100,
            tokens_used=0,
            dimensions_skipped=[
                {"dimension": "hero:content_rendering", "reason": "evaluation_failed"},
                {"dimension": "hero:icon_media", "reason": "evaluation_failed"},
            ],
        )
        report = build_visual_report([result])
        assert report["dimensions_skipped_total"] == 2
        assert "2 dimension(s) skipped" in report["summary"]
        assert report["pages"][0]["dimensions_skipped"] == result.dimensions_skipped

    def test_report_omits_skip_fields_when_none_skipped(self) -> None:
        result = PageVisualResult(route="/", viewport="desktop", visual_score=100, tokens_used=500)
        report = build_visual_report([result])
        assert "dimensions_skipped_total" not in report
        assert "dimensions_skipped" not in report["pages"][0]


# ── Evaluate Captures Tests ──────────────────────────────────────────


@pytest.mark.skipif(not _has_pillow, reason="Pillow not installed")
class TestEvaluateCaptures:
    """Test the main evaluation entry point (with mocked LLM calls)."""

    def _make_capture(self, tmp_path: Path) -> CapturedPage:
        """Create a CapturedPage with a real image file."""
        from PIL import Image

        img = Image.new("RGB", (400, 200), color="red")
        img_path = tmp_path / "index-desktop-hero.png"
        img.save(img_path)

        return CapturedPage(
            route="/",
            viewport="desktop",
            sections=[
                CapturedSection(
                    section_type="hero",
                    path=str(img_path),
                    width=400,
                    height=200,
                    tokens_est=107,
                )
            ],
            total_tokens_est=107,
        )

    @patch("dazzle.core.composition_visual._call_vision_api")
    def test_evaluates_section(self, mock_api: Any, tmp_path: Any) -> None:
        mock_api.return_value = (
            json.dumps({"findings": []}),
            500,
        )
        capture = self._make_capture(tmp_path)

        results = evaluate_captures(
            [capture],
            dimensions=["content_rendering"],
        )

        assert len(results) == 1
        assert results[0].route == "/"
        assert results[0].tokens_used == 500
        assert mock_api.called

    @patch("dazzle.core.composition_visual._call_vision_api")
    def test_collects_findings(self, mock_api: Any, tmp_path: Any) -> None:
        mock_api.return_value = (
            json.dumps(
                {
                    "findings": [
                        {
                            "section": "hero",
                            "category": "content_rendering",
                            "severity": "high",
                            "finding": "Missing headline",
                            "evidence": "White block",
                            "remediation": "Load content",
                        }
                    ]
                }
            ),
            800,
        )
        capture = self._make_capture(tmp_path)

        results = evaluate_captures(
            [capture],
            dimensions=["content_rendering"],
        )

        assert len(results[0].findings) == 1
        assert results[0].findings[0].severity == "high"
        assert results[0].visual_score == 80

    @patch("dazzle.core.composition_visual._call_vision_api")
    def test_token_budget_stops_evaluation(self, mock_api: Any, tmp_path: Any) -> None:
        mock_api.return_value = (json.dumps({"findings": []}), 100)
        capture = self._make_capture(tmp_path)

        evaluate_captures(
            [capture],
            dimensions=["content_rendering", "icon_media", "layout_overflow"],
            token_budget=150,
        )

        # Should stop after 2 calls (100 + 100 > 150 on 2nd check)
        assert mock_api.call_count <= 2

    @patch("dazzle.core.composition_visual._call_vision_api")
    def test_skips_responsive_for_desktop(self, mock_api: Any, tmp_path: Any) -> None:
        mock_api.return_value = (json.dumps({"findings": []}), 100)
        capture = self._make_capture(tmp_path)

        results = evaluate_captures(
            [capture],
            dimensions=["responsive_fidelity"],
        )

        # Desktop viewport should skip responsive_fidelity
        assert not mock_api.called
        assert results[0].dimensions_evaluated == []

    @patch("dazzle.core.composition_visual._call_vision_api")
    def test_missing_screenshot_skipped(self, mock_api: Any, tmp_path: Any) -> None:
        capture = CapturedPage(
            route="/",
            viewport="desktop",
            sections=[
                CapturedSection(
                    section_type="hero",
                    path="/nonexistent/path.png",
                    width=400,
                    height=200,
                    tokens_est=107,
                )
            ],
        )

        results = evaluate_captures(
            [capture],
            dimensions=["content_rendering"],
        )

        assert not mock_api.called
        assert results[0].dimensions_evaluated == []
        assert len(results[0].dimensions_skipped) == 1
        assert results[0].dimensions_skipped[0]["dimension"] == "hero:content_rendering"

    @patch("dazzle.core.composition_visual._call_vision_api")
    def test_api_failure_tracked_as_skipped(self, mock_api: Any, tmp_path: Any) -> None:
        mock_api.side_effect = RuntimeError("API key not set")
        capture = self._make_capture(tmp_path)

        results = evaluate_captures(
            [capture],
            dimensions=["content_rendering"],
        )

        assert results[0].dimensions_evaluated == []
        assert len(results[0].dimensions_skipped) == 1
        assert results[0].tokens_used == 0


# ── MCP Handler Tests ────────────────────────────────────────────────


@pytest.mark.skipif(not _has_pillow, reason="Pillow not installed")
class TestAnalyzeCompositionHandler:
    """Test the analyze MCP handler."""

    def test_no_captures_dir(self, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import (
            analyze_composition_handler,
        )

        result = analyze_composition_handler(tmp_path, {"operation": "analyze"})
        data = json.loads(result)
        assert "error" in data
        assert "No captures found" in data["error"]

    def test_empty_captures_dir(self, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import (
            analyze_composition_handler,
        )

        captures_dir = tmp_path / ".dazzle" / "composition" / "captures"
        captures_dir.mkdir(parents=True)

        result = analyze_composition_handler(tmp_path, {"operation": "analyze"})
        data = json.loads(result)
        assert "error" in data

    def test_invalid_focus_dimensions(self, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import (
            analyze_composition_handler,
        )

        captures_dir = tmp_path / ".dazzle" / "composition" / "captures"
        captures_dir.mkdir(parents=True)
        # Create a dummy capture file
        from PIL import Image

        img = Image.new("RGB", (100, 100))
        img.save(captures_dir / "index-desktop-hero.png")

        result = analyze_composition_handler(
            tmp_path,
            {"operation": "analyze", "focus": ["nonexistent_dimension"]},
        )
        data = json.loads(result)
        assert "error" in data
        assert "No valid dimensions" in data["error"]

    @patch("dazzle.core.composition_visual._call_vision_api")
    def test_returns_report(self, mock_api: Any, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import (
            analyze_composition_handler,
        )

        mock_api.return_value = (json.dumps({"findings": []}), 500)

        captures_dir = tmp_path / ".dazzle" / "composition" / "captures"
        captures_dir.mkdir(parents=True)
        from PIL import Image

        img = Image.new("RGB", (1280, 400))
        img.save(captures_dir / "index-desktop-hero.png")

        result = analyze_composition_handler(
            tmp_path,
            {"operation": "analyze", "focus": ["content_rendering"]},
        )
        data = json.loads(result)
        assert "visual_score" in data
        assert "pages" in data
        assert "markdown" in data


# ── Dimension Configuration Tests ────────────────────────────────────


class TestDimensionConfig:
    """Test dimension configuration constants."""

    def test_all_dimensions_have_preprocessing(self) -> None:
        for dim in DIMENSIONS:
            assert dim in DIMENSION_PREPROCESSING

    def test_mobile_only_is_subset(self) -> None:
        assert MOBILE_ONLY_DIMENSIONS.issubset(set(DIMENSIONS))

    def test_six_dimensions(self) -> None:
        assert len(DIMENSIONS) == 6


# ── Load Captures Tests ──────────────────────────────────────────────


@pytest.mark.skipif(not _has_pillow, reason="Pillow not installed")
class TestLoadCapturesFromDir:
    """Test reconstructing captures from filesystem."""

    def test_groups_by_route_viewport(self, tmp_path: Any) -> None:
        from PIL import Image

        from dazzle.mcp.server.handlers.composition import (
            _load_captures_from_dir,
        )

        img = Image.new("RGB", (1280, 400))
        img.save(tmp_path / "index-desktop-hero.png")
        img.save(tmp_path / "index-desktop-features.png")
        img.save(tmp_path / "index-desktop-full.png")

        captures = _load_captures_from_dir(tmp_path)
        assert len(captures) == 1
        assert captures[0].route == "/"
        assert captures[0].viewport == "desktop"
        assert len(captures[0].sections) == 2
        assert captures[0].full_page is not None

    def test_skips_preprocessed_variants(self, tmp_path: Any) -> None:
        from PIL import Image

        from dazzle.mcp.server.handlers.composition import (
            _load_captures_from_dir,
        )

        img = Image.new("RGB", (1280, 400))
        img.save(tmp_path / "index-desktop-hero.png")
        img.save(tmp_path / "index-desktop-hero-opt.png")
        img.save(tmp_path / "index-desktop-hero-blur.png")

        captures = _load_captures_from_dir(tmp_path)
        assert len(captures) == 1
        assert len(captures[0].sections) == 1

    def test_empty_dir(self, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import (
            _load_captures_from_dir,
        )

        captures = _load_captures_from_dir(tmp_path)
        assert captures == []

    def test_multiple_viewports(self, tmp_path: Any) -> None:
        from PIL import Image

        from dazzle.mcp.server.handlers.composition import (
            _load_captures_from_dir,
        )

        img = Image.new("RGB", (1280, 400))
        img.save(tmp_path / "index-desktop-hero.png")
        img.save(tmp_path / "index-mobile-hero.png")

        captures = _load_captures_from_dir(tmp_path)
        assert len(captures) == 2
        viewports = {c.viewport for c in captures}
        assert viewports == {"desktop", "mobile"}
