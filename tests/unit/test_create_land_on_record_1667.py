"""#1667: create lands on the new record; peek/nested stay put."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import BaseModel

from dazzle.http.runtime.handlers.write_handlers import (
    _nested_on_other_hub,
    create_create_handler,
)
from dazzle.http.runtime.route_generator import HandlerConfig, RouteSpec


class _Create(BaseModel):
    title: str


def _handler(*, slug: str = "invoice") -> Any:
    service = AsyncMock()
    uid = str(uuid4())
    service.execute = AsyncMock(return_value={"id": uid, "title": "Test"})
    handler = create_create_handler(
        RouteSpec(
            handler=HandlerConfig(entity_name="Invoice"),
            service=service,
            input_schema=_Create,
        ),
        entity_slug=slug,
    )
    return handler, uid


def _htmx_request(*, peek: bool = False, current: str | None = None) -> MagicMock:
    request = MagicMock()
    headers = {"HX-Request": "true", "content-type": "application/json"}
    if current:
        headers["hx-current-url"] = current
    request.headers = headers
    request.json = AsyncMock(return_value={"title": "Test"})
    request.query_params = {"peek": "1"} if peek else {}
    return request


def test_nested_on_other_hub() -> None:
    assert _nested_on_other_hub("http://localhost/app/invoice/abc", "line_item") is True
    assert _nested_on_other_hub("/app/invoice/abc", "invoice") is False
    assert _nested_on_other_hub("/app/workspaces/my_invoices", "invoice") is False
    assert _nested_on_other_hub("/app/invoice", "invoice") is False
    assert _nested_on_other_hub("/app/Invoice/abc", "line_item") is False
    assert _nested_on_other_hub(None, "line_item") is False


@pytest.mark.asyncio
async def test_create_redirects_to_new_record() -> None:
    handler, uid = _handler()
    resp = await handler(_htmx_request(current="http://localhost/app/invoice"))
    assert resp.headers.get("HX-Redirect") == f"/app/invoice/{uid}"


@pytest.mark.asyncio
async def test_create_from_workspace_redirects() -> None:
    handler, uid = _handler()
    resp = await handler(_htmx_request(current="http://localhost/app/workspaces/my_invoices"))
    assert resp.headers.get("HX-Redirect") == f"/app/invoice/{uid}"


@pytest.mark.asyncio
async def test_peek_create_does_not_redirect() -> None:
    handler, _uid = _handler()
    resp = await handler(_htmx_request(peek=True))
    assert "HX-Redirect" not in resp.headers


@pytest.mark.asyncio
async def test_nested_create_stays_on_other_hub() -> None:
    handler, _uid = _handler(slug="line_item")
    resp = await handler(_htmx_request(current="http://localhost/app/invoice/abc"))
    assert "HX-Redirect" not in resp.headers
