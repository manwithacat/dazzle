"""Real-Postgres proof that rich-text values are sanitised before storage (ship T).

Before flense ship T nothing called ``clean_rich_text``: a ``widget=rich_text``
field is a plain ``text`` column, so ``POST``/``PUT`` through the generated API
stored the posted HTML as sent and every JSON reader got ``<script>`` and
``onerror=`` back. This boots a three-field DSL (``body`` is rich text on its
surfaces, ``plain`` is not) in ``tmp_path`` against a disposable database,
writes hostile HTML through the generated API and reads it back.

The project lives in ``tmp_path``, so no ``xdist_group`` pin is needed.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_BASE_URL = "http://richtext-probe.local"

_MANIFEST = """[project]
name = "rt_probe"
version = "0.1.0"
root = "rt_probe"

[modules]
paths = ["./dsl"]
"""

_DSL = """module rt_probe
app rt_probe "Rich Text Probe"

entity Note "Note":
  id: uuid pk
  title: str(200) required
  body: text
  plain: text

surface note_create "New Note":
  uses entity Note
  mode: create
  section main:
    field title "Title"
    field body "Body" widget=rich_text rich_text_max_length="400"
    field plain "Plain"

surface note_edit "Edit Note":
  uses entity Note
  mode: edit
  section main:
    field title "Title"
    field body "Body" widget=rich_text rich_text_max_length="400"
    field plain "Plain"

surface note_list "Notes":
  uses entity Note
  mode: list
  section main:
    field title "Title"

surface note_view "Note":
  uses entity Note
  mode: view
  section main:
    field title "Title"
    field body "Body"
    field plain "Plain"
"""

# `<svg/onload=…>` and an entity-encoded `javascript:` href both passed the
# regex denylist the service layer ran on `text` fields until flense ship W
# removed it; only the allowlist sanitiser removes them.
_HOSTILE = (
    '<p>Hi <strong>there</strong> <a href="https://example.com/x">link</a></p>'
    "<script>alert(1)</script>"
    "<svg/onload=alert(2)>"
    '<a href="&#106;avascript:alert(3)">x</a>'
)
_SANITISED = (
    '<p>Hi <strong>there</strong> <a href="https://example.com/x">link</a></p>alert(1)<a>x</a>'
)
# Not a rich-text field: the allowlist sanitiser would escape `<`/`&` and drop
# the span, so a byte-identical read-back proves it was not applied here.
_PLAIN = "a < b & c <em>x</em> <span>y</span>"


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[Any]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL")

    import httpx

    from dazzle.rbac.verifier import _build_asgi_app, _DisposableDatabase
    from dazzle.testing.http_policies import csrf_headers, prime_csrf_cookie

    root = tmp_path / "rt_probe"
    (root / "dsl").mkdir(parents=True)
    (root / "dazzle.toml").write_text(_MANIFEST)
    (root / "dsl" / "app.dsl").write_text(_DSL)

    async with _DisposableDatabase(_PG_URL) as db_url:
        built = _build_asgi_app(root, db_url)
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=built.app), base_url=_BASE_URL
            ) as c:
                # Double-submit CSRF: prime the cookie, echo it on every mutation.
                await prime_csrf_cookie(c, _BASE_URL)
                c.headers.update(csrf_headers(c))
                yield c
        finally:
            db_manager = getattr(built.builder, "_db_manager", None)
            if db_manager is not None:
                db_manager.close_pool()


async def test_create_and_update_store_sanitised_html(client: Any) -> None:
    resp = await client.post("/notes", json={"title": "First", "body": _HOSTILE, "plain": _PLAIN})
    assert resp.status_code in (200, 201), resp.text[:400]
    note_id = resp.json()["id"]

    stored = (await client.get(f"/notes/{note_id}")).json()
    assert stored["body"] == _SANITISED
    assert "<script" not in stored["body"] and "onload" not in stored["body"]
    assert "avascript" not in stored["body"]
    assert stored["plain"] == _PLAIN  # not a rich-text field: byte-identical

    resp = await client.put(
        f"/notes/{note_id}",
        json={"title": "First", "body": '<p onclick="x()">edited</p><script>1</script>'},
    )
    assert resp.status_code == 200, resp.text[:400]
    stored = (await client.get(f"/notes/{note_id}")).json()
    assert stored["body"] == "<p>edited</p>1"


async def test_over_cap_value_is_rejected_not_stored(client: Any) -> None:
    resp = await client.post("/notes", json={"title": "Long", "body": "<p>" + "x" * 500 + "</p>"})
    assert resp.status_code == 422, resp.text[:400]
    (err,) = resp.json()["detail"]
    assert err["loc"] == ["body", "body"]
    assert "exceeds 400 characters" in err["msg"]

    listing = (await client.get("/notes")).json()
    assert all(row["title"] != "Long" for row in listing["items"])


# Flense ship W: the service layer no longer runs its regex denylist over
# `text` fields. It matched ` one=two` as an event-handler attribute and
# deleted it, from plain text and from bleach's rich-text output alike.
_PLAIN_W = "I set one=two today; a<b and c > d, <x onclick=1> stays text"
_RICH_W = '<p>I set one=two today, <a href="https://example.com/?a=b">see</a></p>'


async def test_plain_text_round_trips_byte_identical(client: Any) -> None:
    resp = await client.post("/notes", json={"title": "W", "plain": _PLAIN_W})
    assert resp.status_code in (200, 201), resp.text[:400]
    note_id = resp.json()["id"]
    assert (await client.get(f"/notes/{note_id}")).json()["plain"] == _PLAIN_W

    edited = _PLAIN_W + " (onload=again)"
    resp = await client.put(f"/notes/{note_id}", json={"title": "W", "plain": edited})
    assert resp.status_code == 200, resp.text[:400]
    assert (await client.get(f"/notes/{note_id}")).json()["plain"] == edited


async def test_rich_text_is_cleaned_once_not_mangled_by_the_service(client: Any) -> None:
    from dazzle.http.runtime.richtext_field import clean_rich_text

    resp = await client.post("/notes", json={"title": "W", "body": _RICH_W})
    assert resp.status_code in (200, 201), resp.text[:400]
    note_id = resp.json()["id"]
    stored = (await client.get(f"/notes/{note_id}")).json()["body"]
    assert stored == clean_rich_text(_RICH_W)
    assert "one=two" in stored
