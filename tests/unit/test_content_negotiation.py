"""Tests for Accept header content negotiation in route_generator (#348, #349, #356)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.responses import RedirectResponse

from dazzle_back.runtime.route_generator import (
    _is_htmx_request,
    _list_handler_body,
    _wants_html,
)


def _req(**headers: str) -> SimpleNamespace:
    """Build a minimal request-like object."""
    return SimpleNamespace(headers=headers)


class TestIsHtmxRequest:
    """_is_htmx_request() should only match genuine HTMX requests (#349)."""

    def test_htmx_header(self) -> None:
        """HX-Request header is the only signal."""
        assert _is_htmx_request(_req(**{"HX-Request": "true"})) is True

    def test_accept_text_html_is_not_htmx(self) -> None:
        """Accept: text/html alone is NOT an HTMX request (#349)."""
        assert _is_htmx_request(_req(Accept="text/html")) is False

    def test_browser_accept_is_not_htmx(self) -> None:
        """Standard browser Accept header is NOT an HTMX request (#349)."""
        browser_accept = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        )
        assert _is_htmx_request(_req(Accept=browser_accept)) is False

    def test_json_accept(self) -> None:
        """application/json should not match."""
        assert _is_htmx_request(_req(Accept="application/json")) is False

    def test_empty_accept(self) -> None:
        """Missing Accept header should not match."""
        assert _is_htmx_request(_req()) is False

    def test_no_headers_attr(self) -> None:
        """Object without headers attribute should return False."""
        assert _is_htmx_request(object()) is False


class TestWantsHtml:
    """_wants_html() should match HTMX requests and browser navigation (#348)."""

    def test_htmx_header(self) -> None:
        """HX-Request header means wants HTML."""
        assert _wants_html(_req(**{"HX-Request": "true"})) is True

    def test_exact_text_html(self) -> None:
        """Accept: text/html (exact) should match."""
        assert _wants_html(_req(Accept="text/html")) is True

    def test_browser_accept_header(self) -> None:
        """Standard browser Accept header should match (#348)."""
        browser_accept = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        )
        assert _wants_html(_req(Accept=browser_accept)) is True

    def test_json_accept(self) -> None:
        """application/json should not match."""
        assert _wants_html(_req(Accept="application/json")) is False

    def test_wildcard_only(self) -> None:
        """*/* alone should not match (too broad)."""
        assert _wants_html(_req(Accept="*/*")) is False

    def test_empty_accept(self) -> None:
        """Missing Accept header should not match."""
        assert _wants_html(_req()) is False

    def test_no_headers_attr(self) -> None:
        """Object without headers attribute should return False."""
        assert _wants_html(object()) is False

    def test_playwright_accept(self) -> None:
        """Playwright default Accept header should match."""
        assert _wants_html(_req(Accept="text/html,*/*")) is True


def _mock_request(accept: str = "", hx_request: bool = False, query: str = "") -> MagicMock:
    """Build a mock request with headers, url, and query_params for list handler tests."""
    headers: dict[str, str] = {}
    if accept:
        headers["Accept"] = accept
    if hx_request:
        headers["HX-Request"] = "true"

    req = MagicMock()
    req.headers = headers

    # URL with query string
    url = MagicMock()
    url.path = "/employees"
    url.query = query
    req.url = url

    # query_params (truthy when non-empty)
    req.query_params = MagicMock()
    req.query_params.__bool__ = lambda _self: bool(query)
    req.query_params.items = lambda: []

    # state (used by HTMX rendering)
    req.state = SimpleNamespace()

    return req


def _mock_service(items: list | None = None) -> AsyncMock:
    """Build a mock service that returns a list result."""
    svc = AsyncMock()
    svc.execute.return_value = {
        "items": items or [],
        "total": len(items) if items else 0,
        "page": 1,
        "page_size": 20,
    }
    return svc


class TestListContentNegotiation:
    """List handler should redirect browsers to UI route (#356)."""

    @pytest.mark.asyncio
    async def test_browser_gets_redirect(self) -> None:
        """Accept: text/html (no HX-Request) → 302 to /app/{entity}."""
        req = _mock_request(accept="text/html")
        result = await _list_handler_body(
            service=_mock_service(),
            access_spec=None,
            is_authenticated=False,
            user_id=None,
            request=req,
            page=1,
            page_size=20,
            sort=None,
            dir="asc",
            search=None,
            entity_name="Employee",
        )
        assert isinstance(result, RedirectResponse)
        assert result.status_code == 302
        assert result.headers["location"] == "/app/employee"

    @pytest.mark.asyncio
    async def test_browser_redirect_preserves_query_params(self) -> None:
        """Query params should be forwarded in the redirect."""
        req = _mock_request(accept="text/html", query="sort=name&dir=desc")
        result = await _list_handler_body(
            service=_mock_service(),
            access_spec=None,
            is_authenticated=False,
            user_id=None,
            request=req,
            page=1,
            page_size=20,
            sort="name",
            dir="desc",
            search=None,
            entity_name="Employee",
        )
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/app/employee?sort=name&dir=desc"

    @pytest.mark.asyncio
    async def test_htmx_does_not_redirect(self) -> None:
        """HX-Request should NOT redirect — it gets HTML fragments."""
        req = _mock_request(accept="text/html", hx_request=True)
        result = await _list_handler_body(
            service=_mock_service(),
            access_spec=None,
            is_authenticated=False,
            user_id=None,
            request=req,
            page=1,
            page_size=20,
            sort=None,
            dir="asc",
            search=None,
            entity_name="Employee",
        )
        # HTMX rendering may fail (no template renderer in tests), but it
        # should NOT be a RedirectResponse — it falls through to JSON.
        assert not isinstance(result, RedirectResponse)

    @pytest.mark.asyncio
    async def test_json_client_does_not_redirect(self) -> None:
        """Accept: application/json should return JSON (no redirect)."""
        req = _mock_request(accept="application/json")
        result = await _list_handler_body(
            service=_mock_service(items=[]),
            access_spec=None,
            is_authenticated=False,
            user_id=None,
            request=req,
            page=1,
            page_size=20,
            sort=None,
            dir="asc",
            search=None,
            entity_name="Employee",
        )
        assert not isinstance(result, RedirectResponse)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_underscore_entity_name_becomes_hyphenated_slug(self) -> None:
        """Entity 'IBG_Policy' should redirect to /app/ibg-policy."""
        req = _mock_request(accept="text/html")
        result = await _list_handler_body(
            service=_mock_service(),
            access_spec=None,
            is_authenticated=False,
            user_id=None,
            request=req,
            page=1,
            page_size=20,
            sort=None,
            dir="asc",
            search=None,
            entity_name="IBG_Policy",
        )
        assert isinstance(result, RedirectResponse)
        assert result.headers["location"] == "/app/ibg-policy"
