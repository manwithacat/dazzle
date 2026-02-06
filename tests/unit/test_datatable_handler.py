"""Tests for DataTable sort/filter/search query parameter handling."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    query_params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """Build a mock FastAPI Request."""
    req = MagicMock()
    req.query_params = query_params or {}
    req.headers = headers or {}
    req.url.path = "/tasks"
    req.state = MagicMock()
    # Remove htmx attributes so handler returns JSON
    del req.state.htmx_columns
    del req.state.htmx_detail_url
    del req.state.htmx_entity_name
    del req.state.htmx_empty_message
    return req


def _make_service(items: list[dict[str, Any]] | None = None) -> AsyncMock:
    """Build a mock service that returns a paginated result."""
    svc = AsyncMock()
    svc.execute = AsyncMock(
        return_value={
            "items": items or [],
            "total": len(items) if items else 0,
            "page": 1,
            "page_size": 20,
        }
    )
    return svc


# ---------------------------------------------------------------------------
# Import create_list_handler (requires FastAPI)
# ---------------------------------------------------------------------------

pytest.importorskip("fastapi", reason="FastAPI required for handler tests")

from dazzle_back.runtime.route_generator import create_list_handler  # noqa: E402

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestListHandlerSort:
    """Verify sort/dir query params are forwarded to the service."""

    @pytest.mark.asyncio
    async def test_handler_passes_sort_to_service(self) -> None:
        service = _make_service()
        handler = create_list_handler(service)

        request = _make_request()
        await handler(request=request, page=1, page_size=20, sort="title", dir="desc", search=None)

        service.execute.assert_called_once()
        call_kwargs = service.execute.call_args.kwargs
        assert call_kwargs["sort"] == ["-title"]

    @pytest.mark.asyncio
    async def test_handler_sort_asc(self) -> None:
        service = _make_service()
        handler = create_list_handler(service)

        request = _make_request()
        await handler(request=request, page=1, page_size=20, sort="name", dir="asc", search=None)

        call_kwargs = service.execute.call_args.kwargs
        assert call_kwargs["sort"] == ["name"]

    @pytest.mark.asyncio
    async def test_handler_no_sort(self) -> None:
        service = _make_service()
        handler = create_list_handler(service)

        request = _make_request()
        await handler(request=request, page=1, page_size=20, sort=None, dir="asc", search=None)

        call_kwargs = service.execute.call_args.kwargs
        assert call_kwargs["sort"] is None


class TestListHandlerFilter:
    """Verify filter[field] params are extracted from the query string."""

    @pytest.mark.asyncio
    async def test_handler_extracts_filter_params(self) -> None:
        service = _make_service()
        handler = create_list_handler(service)

        request = _make_request(
            query_params={"filter[status]": "active", "filter[priority]": "high"}
        )
        await handler(request=request, page=1, page_size=20, sort=None, dir="asc", search=None)

        call_kwargs = service.execute.call_args.kwargs
        filters = call_kwargs["filters"]
        assert filters is not None
        assert filters["status"] == "active"
        assert filters["priority"] == "high"

    @pytest.mark.asyncio
    async def test_handler_ignores_empty_filter(self) -> None:
        service = _make_service()
        handler = create_list_handler(service)

        request = _make_request(query_params={"filter[status]": ""})
        await handler(request=request, page=1, page_size=20, sort=None, dir="asc", search=None)

        call_kwargs = service.execute.call_args.kwargs
        # Empty filter values should not be included
        assert call_kwargs["filters"] is None


class TestListHandlerSearch:
    """Verify search query param is forwarded to the service."""

    @pytest.mark.asyncio
    async def test_handler_passes_search_to_service(self) -> None:
        service = _make_service()
        handler = create_list_handler(service)

        request = _make_request()
        await handler(request=request, page=1, page_size=20, sort=None, dir="asc", search="foo")

        call_kwargs = service.execute.call_args.kwargs
        assert call_kwargs["search"] == "foo"

    @pytest.mark.asyncio
    async def test_handler_no_search(self) -> None:
        service = _make_service()
        handler = create_list_handler(service)

        request = _make_request()
        await handler(request=request, page=1, page_size=20, sort=None, dir="asc", search=None)

        call_kwargs = service.execute.call_args.kwargs
        assert call_kwargs["search"] is None


class TestListHandlerBackwardCompat:
    """No extra params → service gets sort=None, search=None, filters=None."""

    @pytest.mark.asyncio
    async def test_handler_backward_compat(self) -> None:
        service = _make_service()
        handler = create_list_handler(service)

        request = _make_request()
        await handler(request=request, page=1, page_size=20, sort=None, dir="asc", search=None)

        call_kwargs = service.execute.call_args.kwargs
        assert call_kwargs["sort"] is None
        assert call_kwargs["search"] is None
        assert call_kwargs["filters"] is None
        assert call_kwargs["page"] == 1
        assert call_kwargs["page_size"] == 20
