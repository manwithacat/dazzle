"""Rich-text values are sanitised on every write path (flense ship T, ADR-0057).

``clean_rich_text`` existed with no caller: a ``widget=rich_text`` field is a
plain ``text`` column, so the create/update handlers persisted posted HTML as
sent and JSON API readers got it raw. These tests pin the wiring:

* ``rich_text_fields_by_entity`` derives the per-entity field → cap map from
  surfaces (the only rich-text signal in the IR);
* ``create_create_handler`` / ``create_update_handler`` hand the repository a
  sanitised value, leave non-rich-text fields byte-identical, and 422 an
  over-cap value without writing;
* the experience-form path (the ``_inprocess_create`` invoker) is covered by
  the same create core.

The real-Postgres proof through the generated API is
``tests/integration/test_richtext_sanitise_pg.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import BaseModel

from dazzle.core.ir.richtext import RICH_TEXT_MAX_LENGTH_DEFAULT
from dazzle.http.runtime.richtext_field import rich_text_fields_by_entity
from dazzle.http.runtime.route_generator import (
    HandlerConfig,
    RouteSpec,
    create_create_handler,
    create_update_handler,
)

_HOSTILE = (
    '<p>Hi <strong>there</strong> <a href="https://example.com/x">link</a></p>'
    "<script>alert(1)</script>"
    '<img src=x onerror="alert(2)">'
    '<a href="javascript:alert(3)">bad</a>'
    # Both passed the regex denylist removed in flense ship W:
    "<svg/onload=alert(4)>"
    '<a href="&#106;avascript:alert(5)">enc</a>'
)
_SANITISED = '<p>Hi <strong>there</strong> <a href="https://example.com/x">link</a></p>alert(1)<a>bad</a><a>enc</a>'
# A non-rich-text `text` field carrying markup must reach the repository
# untouched — sanitising is scoped to declared rich-text fields only.
_PLAIN = "a < b && c > d <script>not-html-here</script> &amp; 'quotes'"


class _Schema(BaseModel):
    title: str | None = None
    body: str | None = None
    plain: str | None = None


def _request(payload: dict[str, Any]) -> Any:
    request = MagicMock()
    request.headers = {"content-type": "application/json"}
    request.json = AsyncMock(return_value=payload)
    request.query_params = {}
    request.app.state = MagicMock()
    return request


def _service() -> AsyncMock:
    service = AsyncMock()
    service.execute = AsyncMock(return_value={"id": "new-id"})
    return service


def _written(service: AsyncMock) -> dict[str, Any]:
    service.execute.assert_awaited_once()
    data = service.execute.await_args.kwargs["data"]
    return dict(data.model_dump(exclude_unset=True))


def _create(service: AsyncMock, caps: dict[str, int] | None) -> Any:
    return create_create_handler(
        RouteSpec(
            handler=HandlerConfig(entity_name="Note"),
            service=service,
            input_schema=_Schema,
        ),
        rich_text_fields=caps,
    )


def _update(service: AsyncMock, caps: dict[str, int] | None) -> Any:
    return create_update_handler(
        RouteSpec(
            handler=HandlerConfig(entity_name="Note"),
            service=service,
            input_schema=_Schema,
        ),
        rich_text_fields=caps,
    )


_CAPS = {"body": RICH_TEXT_MAX_LENGTH_DEFAULT}


# ---------------------------------------------------------------------------
# Derivation from surfaces
# ---------------------------------------------------------------------------


def test_rich_text_fields_derived_from_surface_widget(tmp_path: Path) -> None:
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    dsl = tmp_path / "app.dsl"
    dsl.write_text(
        """module rt
app rt "RT"

entity Note "Note":
  id: uuid pk
  title: str(200) required
  body: text
  summary: text
  plain: text

surface note_create "New":
  uses entity Note
  mode: create
  section main:
    field title "Title"
    field body "Body" widget=rich_text
    field summary "Summary" widget=rich_text rich_text_max_length="300"
    field plain "Plain"

surface note_edit "Edit":
  uses entity Note
  mode: edit
  section main:
    field body "Body" widget=rich_text rich_text_max_length="500"
    field summary "Summary" widget=rich_text rich_text_max_length="900"
    field plain "Plain"
"""
    )
    appspec = build_appspec(parse_modules([dsl]), "rt")
    # The largest cap any surface's editor accepts wins; `plain` is absent.
    assert rich_text_fields_by_entity(appspec) == {
        "Note": {"body": RICH_TEXT_MAX_LENGTH_DEFAULT, "summary": 900}
    }


# ---------------------------------------------------------------------------
# Create / update handlers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("op", ["create", "update"])
async def test_handler_sanitises_rich_text_and_leaves_plain_text_alone(op: str) -> None:
    service = _service()
    payload = {"title": "T", "body": _HOSTILE, "plain": _PLAIN}
    if op == "create":
        await _create(service, _CAPS)(_request(payload))
    else:
        await _update(service, _CAPS)(uuid4(), _request(payload))
    written = _written(service)
    assert written["body"] == _SANITISED
    assert "<script" not in written["body"] and "onerror" not in written["body"]
    assert "javascript:" not in written["body"] and "avascript" not in written["body"]
    assert "onload" not in written["body"]
    assert written["plain"] == _PLAIN  # byte-identical: no collateral escaping
    assert written["title"] == "T"


@pytest.mark.asyncio
async def test_handler_without_rich_text_fields_writes_html_unchanged() -> None:
    """Control: an entity with no rich-text surface keeps its value as sent."""
    service = _service()
    await _create(service, None)(_request({"body": _HOSTILE}))
    assert _written(service)["body"] == _HOSTILE


@pytest.mark.asyncio
@pytest.mark.parametrize("op", ["create", "update"])
async def test_over_cap_value_is_422_and_never_written(op: str) -> None:
    service = _service()
    payload = {"body": "<p>" + "x" * 40 + "</p>"}
    with pytest.raises(HTTPException) as exc_info:
        if op == "create":
            await _create(service, {"body": 20})(_request(payload))
        else:
            await _update(service, {"body": 20})(uuid4(), _request(payload))
    assert exc_info.value.status_code == 422
    (err,) = exc_info.value.detail
    assert err["loc"] == ["body", "body"]
    assert err["type"] == "rich_text_too_long"
    assert "exceeds 20 characters" in err["msg"]
    service.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_visually_empty_editor_shell_is_stored_as_null() -> None:
    service = _service()
    await _create(service, _CAPS)(_request({"title": "T", "body": "<p><br></p>"}))
    assert _written(service)["body"] is None


# ---------------------------------------------------------------------------
# Experience-form path: the in-process create invoker runs the same core
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_experience_form_inprocess_create_is_sanitised() -> None:
    service = _service()
    handler = _create(service, _CAPS)
    invoker = handler._inprocess_create
    request = _request({})
    await invoker(None, request, body={"title": "T", "body": _HOSTILE, "plain": _PLAIN})
    request.json.assert_not_awaited()  # pre-parsed body, no re-read
    written = _written(service)
    assert written["body"] == _SANITISED
    assert written["plain"] == _PLAIN


# ---------------------------------------------------------------------------
# Service layer (flense ship W): `text` values are stored as sent
# ---------------------------------------------------------------------------
#
# `CRUDService._sanitize_fields` ran a regex denylist over every `text` field.
# It deleted ` one=two` (matched as an event-handler attribute) from plain
# text, and ran again over the allowlist sanitiser's output for rich text.
# Plain text is data, escaped where it is rendered (see the render tests
# below); rich text is cleaned once, by `clean_rich_text`, in the handler.

_PLAIN_W = "I set one=two today; a<b and c > d, <x onclick=1> & 'q'"
_RICH_W = '<p>I set one=two today, <a href="https://example.com/?a=b">see</a></p>'


class _NoteModel(BaseModel):
    id: Any = None
    title: str | None = None
    body: str | None = None
    plain: str | None = None


def _crud_service() -> Any:
    from dazzle.http.runtime.service_generator import CRUDService
    from dazzle.http.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType

    def _f(name: str, scalar: ScalarType) -> FieldSpec:
        return FieldSpec(name=name, type=FieldType(kind="scalar", scalar_type=scalar))

    spec = EntitySpec(
        name="Note",
        fields=[
            _f("id", ScalarType.UUID),
            _f("title", ScalarType.STR),
            _f("body", ScalarType.TEXT),
            _f("plain", ScalarType.TEXT),
        ],
    )
    return CRUDService(
        entity_name="Note",
        model_class=_NoteModel,
        create_schema=_Schema,
        update_schema=_Schema,
        entity_spec=spec,
    )


@pytest.mark.asyncio
async def test_plain_text_round_trips_byte_identical_through_service() -> None:
    service = _crud_service()
    created = await service.create(_Schema(title="T", plain=_PLAIN_W))
    assert (await service.read(created.id)).plain == _PLAIN_W
    edited = _PLAIN_W + " (onload=again)"
    await service.update(created.id, _Schema(plain=edited))
    assert (await service.read(created.id)).plain == edited


@pytest.mark.asyncio
async def test_str_field_still_has_tags_stripped() -> None:
    """Control: single-line `str` fields keep the #135 tag strip."""
    service = _crud_service()
    created = await service.create(_Schema(title="<b>Bold</b> one=two"))
    assert (await service.read(created.id)).title == "Bold one=two"


@pytest.mark.asyncio
async def test_rich_text_is_cleaned_once_through_handler_and_service() -> None:
    from dazzle.http.runtime.richtext_field import clean_rich_text

    service = _crud_service()
    await _create(service, _CAPS)(_request({"title": "T", "body": _HOSTILE + _RICH_W}))
    (stored,) = service._store.values()
    assert stored.body == clean_rich_text(_HOSTILE + _RICH_W)
    assert "one=two" in stored.body


# ---------------------------------------------------------------------------
# The render side of the ship W decision: plain text is escaped on output
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("truncate", [True, False])
def test_entity_cell_renderer_escapes_plain_text(truncate: bool) -> None:
    """List rows and the detail seam (`fragment_adapter`) share this core."""
    from dazzle.render.fragment.renderer._data_row import _render_cell_display

    html = _render_cell_display({"type": "text"}, "<script>x</script> one=two", truncate=truncate)
    assert "<script>" not in html
    assert "&lt;script&gt;x&lt;/script&gt; one=two" in html


def test_workspace_region_cell_escapes_plain_text() -> None:
    from dazzle.render.fragment import RawHTML
    from dazzle.render.fragment.region._shared import _render_typed_value

    frag = _render_typed_value({"plain": "<img src=x onerror=1>"}, {"key": "plain"})
    assert isinstance(frag, RawHTML)
    assert frag.html == "&lt;img src=x onerror=1&gt;"
