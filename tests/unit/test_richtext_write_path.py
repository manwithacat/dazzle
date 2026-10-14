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
    # Both pass the service layer's regex denylist (`sanitizer.py`):
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
