"""Tests for DataTable sort/filter/search query parameter handling.

The REST list handler forwards ``sort``/``dir``, ``filter[field]`` and
``search`` to the service. It is leftover-honest (cycle 2191): a sort or
filter naming an undeclared field, or a filter value that cannot be a value
of the declared field type, is dropped rather than invented, while the valid
siblings in the same request still ride.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("fastapi", reason="FastAPI required for handler tests")

from dazzle.http.runtime.route_generator import (  # noqa: E402
    HandlerConfig,
    RouteSpec,
    create_list_handler,
)

# The handler reads ``entity_spec.fields``; an AsyncMock would invent a spec
# without names and drop every known sort. ``name`` alone = an untyped field.
_DEFAULT_FIELDS = [SimpleNamespace(name=n) for n in ("id", "title", "name", "status", "priority")]


def _field(name: str, kind: str | None = None, enum: list[str] | None = None) -> Any:
    if enum is not None:
        return SimpleNamespace(name=name, type=SimpleNamespace(enum_values=enum))
    return SimpleNamespace(name=name, type=SimpleNamespace(kind=kind))


def _request(query_params: dict[str, str] | None = None) -> MagicMock:
    req = MagicMock()
    req.query_params = query_params or {}
    req.headers = {}
    req.url.path = "/tasks"
    req.state = MagicMock()
    # Remove htmx attributes so the handler returns JSON
    del req.state.htmx_columns
    del req.state.htmx_detail_url
    del req.state.htmx_entity_name
    del req.state.htmx_empty_message
    return req


async def _service_kwargs(
    fields: list[Any] | None = None,
    query_params: dict[str, str] | None = None,
    **handler_kwargs: Any,
) -> dict[str, Any]:
    """Run the list handler once; return the kwargs it passed to service.execute."""
    service = AsyncMock()
    service.execute = AsyncMock(return_value={"items": [], "total": 0, "page": 1, "page_size": 20})
    service.entity_spec = SimpleNamespace(
        fields=fields if fields is not None else _DEFAULT_FIELDS, temporal=None
    )
    handler = create_list_handler(RouteSpec(handler=HandlerConfig(), service=service))
    call: dict[str, Any] = {"page": 1, "page_size": 20, "sort": None, "dir": "asc", "search": None}
    call.update(handler_kwargs)
    await handler(request=_request(query_params), **call)
    service.execute.assert_called_once()
    return service.execute.call_args.kwargs


@pytest.mark.asyncio
async def test_no_params_forwards_none_and_paging() -> None:
    kwargs = await _service_kwargs(q=None)
    assert (kwargs["sort"], kwargs["search"], kwargs["filters"]) == (None, None, None)
    assert (kwargs["page"], kwargs["page_size"]) == (1, 20)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("sort", "direction", "expected"),
    [
        pytest.param("title", "desc", ["-title"], id="desc-prefixes-minus"),
        pytest.param("name", "asc", ["name"], id="asc"),
        pytest.param("zzz", "desc", None, id="leftover-sort-dropped"),
    ],
)
async def test_sort(sort: str, direction: str, expected: list[str] | None) -> None:
    assert (await _service_kwargs(sort=sort, dir=direction))["sort"] == expected


@pytest.mark.asyncio
async def test_search_forwarded() -> None:
    assert (await _service_kwargs(search="foo", q=None))["search"] == "foo"


_STATUS_ENUM = _field("status", enum=["open", "in_progress", "resolved", "closed"])
_UUID = "12345678-1234-5678-1234-567812345678"


def _typed(field: Any) -> list[Any]:
    """The typed field next to the untyped ``id`` / ``title`` siblings."""
    return [SimpleNamespace(name="id"), SimpleNamespace(name="title"), field]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fields", "query", "expected"),
    [
        pytest.param(
            None,
            {"filter[status]": "active", "filter[priority]": "high"},
            {"status": "active", "priority": "high"},
            id="filter-params-extracted",
        ),
        pytest.param(None, {"filter[status]": ""}, None, id="empty-value-ignored"),
        pytest.param(
            None,
            {"filter[zzz]": "Ada", "filter[ghost]": "1", "filter[status]": "open"},
            {"status": "open"},
            id="undeclared-field-dropped",
        ),
        # Per-type value checks: a junk value is dropped while the valid
        # sibling rides; a valid value of the declared type rides.
        pytest.param(
            _typed(_STATUS_ENUM),
            {"filter[status]": "zzz", "filter[title]": "Ada"},
            {"title": "Ada"},
            id="enum.leftover-dropped",
        ),
        pytest.param(
            [_STATUS_ENUM], {"filter[status]": "resolved"}, {"status": "resolved"}, id="enum.valid"
        ),
        pytest.param(
            None,
            {"filter[id]": "zzz", "filter[title]": "Ada"},
            {"title": "Ada"},
            id="id.leftover-dropped",
        ),
        pytest.param(None, {"filter[id]": _UUID}, {"id": _UUID}, id="id.uuid-valid"),
        pytest.param(
            _typed(_field("created_at", "datetime")),
            {"filter[created_at]": "zzz", "filter[title]": "Ada"},
            {"title": "Ada"},
            id="datetime.leftover-dropped",
        ),
        pytest.param(
            [_field("created_at", "datetime"), _field("due_date", "date")],
            {"filter[created_at]": "2026-07-01T09:00:00"},
            {"created_at": "2026-07-01T09:00:00"},
            id="datetime.valid",
        ),
        pytest.param(
            _typed(_field("is_active", "bool")),
            {"filter[is_active]": "zzz", "filter[title]": "Ada"},
            {"title": "Ada"},
            id="bool.leftover-dropped",
        ),
        pytest.param(
            [_field("is_active", "bool")],
            {"filter[is_active]": "true"},
            {"is_active": "true"},
            id="bool.valid",
        ),
        pytest.param(
            _typed(_field("amount", "int")),
            {"filter[amount]": "zzz", "filter[title]": "Ada"},
            {"title": "Ada"},
            id="int.leftover-dropped",
        ),
        pytest.param(
            [_field("amount", "int")], {"filter[amount]": "42"}, {"amount": "42"}, id="int.valid"
        ),
        pytest.param(
            _typed(_field("email", "email")),
            {"filter[email]": "zzz", "filter[title]": "Ada"},
            {"title": "Ada"},
            id="email.leftover-dropped",
        ),
        pytest.param(
            [_field("email", "email")],
            {"filter[email]": "ada@example.com"},
            {"email": "ada@example.com"},
            id="email.valid",
        ),
        pytest.param(
            _typed(_field("preview_url", "url")),
            {"filter[preview_url]": "zzz", "filter[title]": "Ada"},
            {"title": "Ada"},
            id="url.leftover-dropped",
        ),
        pytest.param(
            [_field("preview_url", "url")],
            {"filter[preview_url]": "https://placehold.co/400"},
            {"preview_url": "https://placehold.co/400"},
            id="url.valid",
        ),
        pytest.param(
            _typed(_field("slug", "slug")),
            {"filter[slug]": "ab", "filter[title]": "Ada"},
            {"title": "Ada"},
            id="slug.too-short-dropped",
        ),
        pytest.param(
            [_field("slug", "slug")], {"filter[slug]": "acme"}, {"slug": "acme"}, id="slug.valid"
        ),
        pytest.param(
            _typed(_field("file", "file")),
            {"filter[file]": "zzz", "filter[title]": "Ada"},
            {"title": "Ada"},
            id="file.leftover-dropped",
        ),
        pytest.param(
            [_field("file", "file")],
            {"filter[file]": "report.pdf"},
            {"file": "report.pdf"},
            id="file.valid",
        ),
        pytest.param(
            _typed(_field("preferences", "json")),
            {"filter[preferences]": "zzz", "filter[title]": "Ada"},
            {"title": "Ada"},
            id="json.leftover-dropped",
        ),
        pytest.param(
            [_field("preferences", "json")],
            {"filter[preferences]": '{"theme":"dark"}'},
            {"preferences": '{"theme":"dark"}'},
            id="json.valid",
        ),
    ],
)
async def test_filters(
    fields: list[Any] | None, query: dict[str, str], expected: dict[str, str] | None
) -> None:
    assert (await _service_kwargs(fields, query))["filters"] == expected
