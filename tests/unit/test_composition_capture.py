"""Tests for the composition capture pipeline."""

from __future__ import annotations

import importlib.util
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.core.composition_capture import (
    CapturedPage,
    CapturedSection,
    ElementGeometry,
    SectionGeometry,
    estimate_tokens,
    preprocess_standard,
)

# ── Token Estimation Tests ───────────────────────────────────────────


class TestEstimateTokens:
    """Test Claude vision token cost estimation."""

    def test_small_image(self) -> None:
        # 800x300 → 800*300/750 = 320
        assert estimate_tokens(800, 300) == 320

    def test_standard_section_crop(self) -> None:
        # 1280x400 → 1280*400/750 ≈ 682
        tokens = estimate_tokens(1280, 400)
        assert 680 <= tokens <= 685

    def test_full_page(self) -> None:
        # 1280x4000 → rescaled to 1568/4000 * (1280x4000)
        # After rescaling: 501x1568 → 501*1568/750 ≈ 1048
        tokens = estimate_tokens(1280, 4000)
        assert 1000 <= tokens <= 1100

    def test_large_image_rescaled(self) -> None:
        # 2000x2000 → rescaled to 1568x1568
        # 1568*1568/750 ≈ 3278
        tokens = estimate_tokens(2000, 2000)
        assert 3200 <= tokens <= 3300

    def test_small_image_not_rescaled(self) -> None:
        # 500x300 → no rescaling, 500*300/750 = 200
        assert estimate_tokens(500, 300) == 200

    def test_minimum_one_token(self) -> None:
        assert estimate_tokens(1, 1) == 1

    def test_exact_max_edge(self) -> None:
        # 1568x100 → exactly at limit, no rescaling
        tokens = estimate_tokens(1568, 100)
        assert tokens == int(1568 * 100 / 750)

    def test_just_over_max_edge(self) -> None:
        # 1569x100 → just over limit, gets rescaled
        tokens = estimate_tokens(1569, 100)
        # After rescale: 1568x99
        expected = int(1568 * int(100 * 1568 / 1569) / 750)
        assert abs(tokens - expected) <= 1


# ── Image Preprocessing Tests ────────────────────────────────────────


_has_pillow = importlib.util.find_spec("PIL") is not None


@pytest.mark.skipif(not _has_pillow, reason="Pillow not installed")
class TestPreprocessStandard:
    """Test standard image preprocessing for token efficiency."""

    def test_small_image_unchanged(self, tmp_path: Any) -> None:
        """Image under max_edge is saved as-is (with optimize)."""
        from PIL import Image

        img = Image.new("RGB", (800, 400), color="red")
        src = tmp_path / "test.png"
        img.save(src)

        result = preprocess_standard(src)
        assert result.name == "test-opt.png"
        assert result.exists()

        out_img = Image.open(result)
        assert out_img.size == (800, 400)

    def test_large_image_resized(self, tmp_path: Any) -> None:
        """Image over max_edge is resized proportionally."""
        from PIL import Image

        img = Image.new("RGB", (3000, 1500), color="blue")
        src = tmp_path / "big.png"
        img.save(src)

        result = preprocess_standard(src)
        out_img = Image.open(result)
        # Longest edge should be ≤1568 (int truncation may give 1567)
        assert max(out_img.size) <= 1568
        assert max(out_img.size) >= 1566
        # Aspect ratio preserved (2:1)
        assert abs(out_img.size[0] / out_img.size[1] - 2.0) < 0.01

    def test_custom_max_edge(self, tmp_path: Any) -> None:
        """Custom max_edge is respected."""
        from PIL import Image

        img = Image.new("RGB", (2000, 1000), color="green")
        src = tmp_path / "custom.png"
        img.save(src)

        result = preprocess_standard(src, max_edge=1000)
        out_img = Image.open(result)
        assert max(out_img.size) == 1000

    def test_output_path_suffix(self, tmp_path: Any) -> None:
        """Output file gets -opt suffix."""
        from PIL import Image

        img = Image.new("RGB", (100, 100))
        src = tmp_path / "original.png"
        img.save(src)

        result = preprocess_standard(src)
        assert result.stem == "original-opt"
        assert result.suffix == ".png"

    def test_without_pillow(self, tmp_path: Any) -> None:
        """Returns original path if Pillow not available."""
        src = tmp_path / "test.png"
        src.write_bytes(b"fake png")

        with patch.dict("sys.modules", {"PIL": None, "PIL.Image": None}):
            # Re-import to test the ImportError path
            import importlib

            import dazzle.core.composition_capture as mod

            importlib.reload(mod)
            result = mod.preprocess_standard(src)
            assert result == src
            # Reload again to restore normal state
            importlib.reload(mod)


# ── Data Model Tests ─────────────────────────────────────────────────


class TestCapturedModels:
    """Test capture data models."""

    def test_captured_section_fields(self) -> None:
        sec = CapturedSection(
            section_type="hero",
            path="/tmp/hero.png",
            width=1280,
            height=400,
            tokens_est=682,
        )
        assert sec.section_type == "hero"
        assert sec.tokens_est == 682

    def test_captured_page_defaults(self) -> None:
        page = CapturedPage(route="/", viewport="desktop")
        assert page.sections == []
        assert page.full_page is None
        assert page.total_tokens_est == 0

    def test_captured_page_serialization(self) -> None:
        from dataclasses import asdict

        page = CapturedPage(
            route="/",
            viewport="desktop",
            sections=[CapturedSection("hero", "/tmp/hero.png", 1280, 400, 682)],
            full_page="/tmp/full.png",
            total_tokens_est=682,
        )
        data = asdict(page)
        assert data["route"] == "/"
        assert len(data["sections"]) == 1
        assert data["sections"][0]["section_type"] == "hero"

    def test_element_geometry_fields(self) -> None:
        geo = ElementGeometry(x=0, y=100, width=1280, height=400)
        assert geo.x == 0
        assert geo.y == 100
        assert geo.width == 1280
        assert geo.height == 400

    def test_section_geometry_defaults(self) -> None:
        sec_geo = SectionGeometry(section=ElementGeometry(0, 0, 1280, 400))
        assert sec_geo.content is None
        assert sec_geo.media is None
        assert sec_geo.viewport_height == 0

    def test_section_geometry_with_children(self) -> None:
        geo = SectionGeometry(
            section=ElementGeometry(0, 0, 1280, 400),
            content=ElementGeometry(0, 0, 640, 400),
            media=ElementGeometry(640, 0, 640, 400),
            viewport_height=720,
        )
        assert geo.content is not None
        assert geo.media is not None
        assert geo.viewport_height == 720

    def test_captured_section_with_geometry(self) -> None:
        geo = SectionGeometry(section=ElementGeometry(0, 0, 1280, 400))
        sec = CapturedSection(
            section_type="hero",
            path="/tmp/hero.png",
            width=1280,
            height=400,
            tokens_est=682,
            geometry=geo,
        )
        assert sec.geometry is not None
        assert sec.geometry.section.width == 1280

    def test_captured_section_geometry_serialization(self) -> None:
        from dataclasses import asdict

        geo = SectionGeometry(
            section=ElementGeometry(0, 100, 1280, 400),
            content=ElementGeometry(0, 100, 640, 380),
            media=ElementGeometry(640, 100, 640, 380),
            viewport_height=720,
        )
        sec = CapturedSection("hero", "/tmp/hero.png", 1280, 400, 682, geometry=geo)
        data = asdict(sec)
        assert data["geometry"]["section"]["x"] == 0
        assert data["geometry"]["content"]["width"] == 640
        assert data["geometry"]["media"]["x"] == 640
        assert data["geometry"]["viewport_height"] == 720

    def test_captured_page_viewport_height(self) -> None:
        page = CapturedPage(route="/", viewport="desktop", viewport_height=720)
        assert page.viewport_height == 720


# ── MCP Handler Tests ────────────────────────────────────────────────


class TestCaptureCompositionHandler:
    """Test the capture MCP handler."""

    @pytest.mark.asyncio
    async def test_requires_base_url(self, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import (
            capture_composition_handler,
        )

        result = await capture_composition_handler(tmp_path, {})
        data = json.loads(result)
        assert "error" in data
        assert "base_url" in data["error"]

    @patch("dazzle.mcp.server.handlers.preflight.check_server_reachable", return_value=None)
    @patch("dazzle.core.composition_capture.capture_page_sections", new_callable=AsyncMock)
    @patch("dazzle.core.sitespec_loader.load_sitespec_with_copy")
    @pytest.mark.asyncio
    async def test_returns_capture_data(
        self,
        mock_load: Any,
        mock_capture: Any,
        mock_preflight: Any,
        tmp_path: Any,
    ) -> None:
        from dazzle.mcp.server.handlers.composition import (
            capture_composition_handler,
        )

        mock_load.return_value = MagicMock(pages=[MagicMock()])
        mock_capture.return_value = [
            CapturedPage(
                route="/",
                viewport="desktop",
                sections=[
                    CapturedSection("hero", "/tmp/hero.png", 1280, 400, 682),
                    CapturedSection("features", "/tmp/features.png", 1280, 500, 853),
                ],
                total_tokens_est=1535,
            )
        ]

        result = await capture_composition_handler(tmp_path, {"base_url": "http://localhost:3000"})
        data = json.loads(result)

        assert data["total_sections"] == 2
        assert data["total_tokens_est"] == 1535
        assert "Captured 2 sections" in data["summary"]
        assert len(data["captures"]) == 1

    @patch("dazzle.mcp.server.handlers.preflight.check_server_reachable", return_value=None)
    @patch("dazzle.core.sitespec_loader.load_sitespec_with_copy")
    @pytest.mark.asyncio
    async def test_empty_sitespec(self, mock_load: Any, mock_preflight: Any, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import (
            capture_composition_handler,
        )

        sitespec = MagicMock(pages=[])
        sitespec.auth_pages.login.enabled = False
        sitespec.auth_pages.signup.enabled = False
        mock_load.return_value = sitespec
        result = await capture_composition_handler(tmp_path, {"base_url": "http://localhost:3000"})
        data = json.loads(result)
        assert data["captures"] == []

    @patch("dazzle.mcp.server.handlers.preflight.check_server_reachable", return_value=None)
    @patch("dazzle.core.composition_capture.capture_page_sections", new_callable=AsyncMock)
    @patch("dazzle.core.sitespec_loader.load_sitespec_with_copy")
    @pytest.mark.asyncio
    async def test_passes_filters(
        self,
        mock_load: Any,
        mock_capture: Any,
        mock_preflight: Any,
        tmp_path: Any,
    ) -> None:
        from dazzle.mcp.server.handlers.composition import (
            capture_composition_handler,
        )

        mock_load.return_value = MagicMock(pages=[MagicMock()])
        mock_capture.return_value = []

        await capture_composition_handler(
            tmp_path,
            {
                "base_url": "http://localhost:3000",
                "pages": ["/about"],
                "viewports": ["mobile"],
            },
        )

        call_kwargs = mock_capture.call_args
        assert call_kwargs.kwargs["routes_filter"] == ["/about"]
        assert call_kwargs.kwargs["viewports"] == ["mobile"]

    @pytest.mark.asyncio
    async def test_playwright_import_error(self, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import (
            capture_composition_handler,
        )

        with (
            patch("dazzle.mcp.server.handlers.preflight.check_server_reachable", return_value=None),
            patch("dazzle.core.sitespec_loader.load_sitespec_with_copy") as mock_load,
            patch(
                "dazzle.core.composition_capture.capture_page_sections",
                new_callable=AsyncMock,
                side_effect=ImportError("Playwright not installed"),
            ),
        ):
            mock_load.return_value = MagicMock(pages=[MagicMock()])
            result = await capture_composition_handler(
                tmp_path, {"base_url": "http://localhost:3000"}
            )
            data = json.loads(result)
            assert "error" in data
            assert "Playwright" in data["error"]
