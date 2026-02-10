"""Tests for the composition style inspection module."""

from __future__ import annotations

import importlib.util
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.core.composition_styles import DEFAULT_PROPERTIES

_has_playwright = importlib.util.find_spec("playwright") is not None

# ── Default Properties Tests ────────────────────────────────────────


class TestDefaultProperties:
    """Test that default properties cover common layout issues."""

    def test_includes_display(self) -> None:
        assert "display" in DEFAULT_PROPERTIES

    def test_includes_flex_direction(self) -> None:
        assert "flex-direction" in DEFAULT_PROPERTIES

    def test_includes_position(self) -> None:
        assert "position" in DEFAULT_PROPERTIES

    def test_includes_width_height(self) -> None:
        assert "width" in DEFAULT_PROPERTIES
        assert "height" in DEFAULT_PROPERTIES

    def test_includes_overflow(self) -> None:
        assert "overflow" in DEFAULT_PROPERTIES


# ── Handler Tests ───────────────────────────────────────────────────


class TestInspectStylesHandler:
    """Test the inspect_styles MCP handler."""

    @pytest.mark.asyncio
    async def test_requires_base_url(self, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import inspect_styles_handler

        result = await inspect_styles_handler(tmp_path, {})
        data = json.loads(result)
        assert "error" in data
        assert "base_url" in data["error"]

    @pytest.mark.asyncio
    async def test_requires_selectors(self, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import inspect_styles_handler

        result = await inspect_styles_handler(tmp_path, {"base_url": "http://localhost:3000"})
        data = json.loads(result)
        assert "error" in data
        assert "selectors" in data["error"]

    @patch(
        "dazzle.core.composition_styles.inspect_computed_styles",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_returns_styles(self, mock_inspect: Any, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import inspect_styles_handler

        mock_inspect.return_value = {
            "hero": {"display": "flex", "flex-direction": "row"},
            "media": {"display": "block", "width": "640px"},
        }

        result = await inspect_styles_handler(
            tmp_path,
            {
                "base_url": "http://localhost:3000",
                "route": "/",
                "selectors": {"hero": ".dz-hero", "media": ".dz-hero-media"},
                "properties": ["display", "flex-direction", "width"],
            },
        )
        data = json.loads(result)

        assert data["styles"]["hero"]["display"] == "flex"
        assert data["styles"]["media"]["width"] == "640px"
        assert data["route"] == "/"
        assert data["selectors_not_found"] == []
        assert "2/2" in data["summary"]

    @patch(
        "dazzle.core.composition_styles.inspect_computed_styles",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_reports_not_found_selectors(self, mock_inspect: Any, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import inspect_styles_handler

        mock_inspect.return_value = {
            "hero": {"display": "flex"},
            "missing": None,
        }

        result = await inspect_styles_handler(
            tmp_path,
            {
                "base_url": "http://localhost:3000",
                "selectors": {"hero": ".dz-hero", "missing": ".nonexistent"},
            },
        )
        data = json.loads(result)

        assert data["selectors_not_found"] == ["missing"]
        assert data["styles"]["missing"] is None
        assert "1/2" in data["summary"]
        assert "missing" in data["summary"]

    @patch(
        "dazzle.core.composition_styles.inspect_computed_styles",
        new_callable=AsyncMock,
    )
    @pytest.mark.asyncio
    async def test_default_route(self, mock_inspect: Any, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import inspect_styles_handler

        mock_inspect.return_value = {"el": {"display": "block"}}

        result = await inspect_styles_handler(
            tmp_path,
            {
                "base_url": "http://localhost:3000",
                "selectors": {"el": ".foo"},
            },
        )
        data = json.loads(result)
        assert data["route"] == "/"
        mock_inspect.assert_called_once_with(
            base_url="http://localhost:3000",
            route="/",
            selectors={"el": ".foo"},
            properties=None,
        )

    @pytest.mark.asyncio
    async def test_playwright_import_error(self, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import inspect_styles_handler

        with patch(
            "dazzle.core.composition_styles.inspect_computed_styles",
            new_callable=AsyncMock,
            side_effect=ImportError("Playwright not installed"),
        ):
            result = await inspect_styles_handler(
                tmp_path,
                {
                    "base_url": "http://localhost:3000",
                    "selectors": {"el": ".foo"},
                },
            )
            data = json.loads(result)
            assert "error" in data
            assert "Playwright" in data["error"]

    @pytest.mark.asyncio
    async def test_navigation_error(self, tmp_path: Any) -> None:
        from dazzle.mcp.server.handlers.composition import inspect_styles_handler

        with patch(
            "dazzle.core.composition_styles.inspect_computed_styles",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Navigation failed: timeout"),
        ):
            result = await inspect_styles_handler(
                tmp_path,
                {
                    "base_url": "http://localhost:3000",
                    "selectors": {"el": ".foo"},
                },
            )
            data = json.loads(result)
            assert "error" in data
            assert "Navigation" in data["error"]


# ── Core Function Tests ─────────────────────────────────────────────


@pytest.mark.skipif(not _has_playwright, reason="Playwright not installed")
class TestInspectComputedStyles:
    """Test the core inspect_computed_styles function."""

    @patch("playwright.async_api.async_playwright")
    @pytest.mark.asyncio
    async def test_extracts_styles_from_elements(self, mock_pw_cls: Any) -> None:
        from dazzle.core.composition_styles import inspect_computed_styles

        # Build mock chain: async_playwright() → context manager → browser → page
        mock_element = MagicMock()
        mock_page = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=mock_element)
        mock_page.evaluate = AsyncMock(return_value={"display": "flex", "width": "1280px"})
        mock_page.set_default_timeout = MagicMock()

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)

        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pw_cls.return_value = mock_cm

        result = await inspect_computed_styles(
            base_url="http://localhost:3000",
            route="/",
            selectors={"hero": ".dz-hero"},
            properties=["display", "width"],
        )

        assert result["hero"] == {"display": "flex", "width": "1280px"}
        mock_page.goto.assert_called_once()
        mock_page.query_selector.assert_called_once_with(".dz-hero")

    @patch("playwright.async_api.async_playwright")
    @pytest.mark.asyncio
    async def test_returns_none_for_missing_selector(self, mock_pw_cls: Any) -> None:
        from dazzle.core.composition_styles import inspect_computed_styles

        mock_page = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=None)
        mock_page.set_default_timeout = MagicMock()

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)

        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pw_cls.return_value = mock_cm

        result = await inspect_computed_styles(
            base_url="http://localhost:3000",
            route="/about",
            selectors={"missing": ".nonexistent"},
        )

        assert result["missing"] is None

    @patch("playwright.async_api.async_playwright")
    @pytest.mark.asyncio
    async def test_uses_default_properties(self, mock_pw_cls: Any) -> None:
        from dazzle.core.composition_styles import inspect_computed_styles

        mock_element = MagicMock()
        mock_page = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=mock_element)
        mock_page.evaluate = AsyncMock(return_value={})
        mock_page.set_default_timeout = MagicMock()

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)

        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pw_cls.return_value = mock_cm

        await inspect_computed_styles(
            base_url="http://localhost:3000",
            route="/",
            selectors={"el": ".foo"},
            # properties=None → uses DEFAULT_PROPERTIES
        )

        # Check evaluate was called with default properties
        call_args = mock_page.evaluate.call_args
        assert call_args[0][1][1] == DEFAULT_PROPERTIES

    @patch("playwright.async_api.async_playwright")
    @pytest.mark.asyncio
    async def test_navigation_failure_raises(self, mock_pw_cls: Any) -> None:
        from dazzle.core.composition_styles import inspect_computed_styles

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=Exception("Timeout"))
        mock_page.set_default_timeout = MagicMock()

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)

        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pw_cls.return_value = mock_cm

        with pytest.raises(RuntimeError, match="Navigation failed"):
            await inspect_computed_styles(
                base_url="http://localhost:3000",
                route="/",
                selectors={"el": ".foo"},
            )

    @patch("playwright.async_api.async_playwright")
    @pytest.mark.asyncio
    async def test_multiple_selectors(self, mock_pw_cls: Any) -> None:
        from dazzle.core.composition_styles import inspect_computed_styles

        mock_el_a = MagicMock()
        mock_el_b = MagicMock()

        mock_page = AsyncMock()
        mock_page.query_selector = AsyncMock(side_effect=[mock_el_a, mock_el_b])
        mock_page.evaluate = AsyncMock(
            side_effect=[
                {"display": "flex"},
                {"display": "block"},
            ]
        )
        mock_page.set_default_timeout = MagicMock()

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)

        mock_pw = AsyncMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_pw_cls.return_value = mock_cm

        result = await inspect_computed_styles(
            base_url="http://localhost:3000",
            route="/",
            selectors={"a": ".class-a", "b": ".class-b"},
            properties=["display"],
        )

        assert result["a"] == {"display": "flex"}
        assert result["b"] == {"display": "block"}
