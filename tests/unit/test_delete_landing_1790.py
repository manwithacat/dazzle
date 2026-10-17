"""#1790: delete stays where it was issued; only the record's own page leaves.

AegisMark: a list-row DELETE answered ``HX-Redirect: /app`` (the blind
parent of ``HX-Current-URL``), so deleting from a list left the list.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from dazzle.http.runtime.handlers.write_handlers import create_delete_handler
from dazzle.http.runtime.route_generator import HandlerConfig, RouteSpec


def _handler(*, soft_delete: bool = False) -> tuple[Any, AsyncMock]:
    service = AsyncMock()
    service.execute = AsyncMock(return_value={"id": str(uuid4()), "title": "Test"})
    handler = create_delete_handler(
        RouteSpec(
            handler=HandlerConfig(entity_name="Invoice"),
            service=service,
            soft_delete=soft_delete,
        ),
        entity_slug="invoice",
    )
    return handler, service


def _request(*, htmx: bool = True, current: str | None = None) -> MagicMock:
    request = MagicMock()
    headers: dict[str, str] = {"HX-Request": "true"} if htmx else {}
    if current:
        headers["hx-current-url"] = current
    request.headers = headers
    request.query_params = {}
    return request


_RID = (
    "0b4e1f2a-7c3d-4e5f-9a1b-2c3d4e5f6a7b"  # fixed: parametrize ids must agree across xdist workers
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("current", "redirect"),
    [
        ("http://localhost/app/invoice", None),  # list page: row swap
        ("http://localhost/app/invoice?page=3&sort=-total", None),
        ("http://localhost/app/workspaces/billing_desk", None),  # job desk
        (f"http://localhost/app/customer/{_RID}", None),  # other entity's hub
        (None, None),  # no HX-Current-URL
        (f"http://localhost/app/invoice/{_RID}", "/app/invoice"),  # own detail page
    ],
)
@pytest.mark.parametrize("soft_delete", [False, True])
async def test_delete_landing_by_origin(
    current: str | None, redirect: str | None, soft_delete: bool
) -> None:
    handler, service = _handler(soft_delete=soft_delete)
    resp = await handler(uuid4(), _request(current=current))
    assert resp.status_code == 200  # 204 is in htmx 4 noSwap
    assert resp.body == b""  # empty HTML: the <tr> outerHTML swap removes the row
    assert resp.headers.get("HX-Redirect") == redirect
    triggers = json.loads(resp.headers["HX-Trigger"])
    assert "entityDeleted" in triggers
    assert "showToast" in triggers
    ops = [c.kwargs.get("operation") for c in service.execute.call_args_list]
    assert ("update" if soft_delete else "delete") in ops


@pytest.mark.asyncio
async def test_non_htmx_delete_returns_dict() -> None:
    handler, _service = _handler()
    resp = await handler(uuid4(), _request(htmx=False))
    assert resp == {"deleted": True}
