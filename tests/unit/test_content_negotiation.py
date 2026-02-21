"""Tests for Accept header content negotiation in route_generator (#348)."""

from __future__ import annotations

from types import SimpleNamespace

from dazzle_back.runtime.route_generator import _is_htmx_request


def _req(**headers: str) -> SimpleNamespace:
    """Build a minimal request-like object."""
    return SimpleNamespace(headers=headers)


class TestIsHtmxRequest:
    """_is_htmx_request() should detect HTMX and standard browser requests."""

    def test_htmx_header(self) -> None:
        """HX-Request header is the primary signal."""
        assert _is_htmx_request(_req(**{"HX-Request": "true"})) is True

    def test_exact_text_html(self) -> None:
        """Accept: text/html (exact) should match."""
        assert _is_htmx_request(_req(Accept="text/html")) is True

    def test_browser_accept_header(self) -> None:
        """Standard browser Accept header should match (#348)."""
        browser_accept = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        )
        assert _is_htmx_request(_req(Accept=browser_accept)) is True

    def test_json_accept(self) -> None:
        """application/json should not match."""
        assert _is_htmx_request(_req(Accept="application/json")) is False

    def test_wildcard_only(self) -> None:
        """*/* alone should not match (too broad)."""
        assert _is_htmx_request(_req(Accept="*/*")) is False

    def test_empty_accept(self) -> None:
        """Missing Accept header should not match."""
        assert _is_htmx_request(_req()) is False

    def test_no_headers_attr(self) -> None:
        """Object without headers attribute should return False."""
        assert _is_htmx_request(object()) is False

    def test_playwright_accept(self) -> None:
        """Playwright default Accept header should match."""
        assert _is_htmx_request(_req(Accept="text/html,*/*")) is True
