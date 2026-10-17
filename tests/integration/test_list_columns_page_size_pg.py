"""Real-Postgres proof of the #1792 column grammar and `page_size:`.

A region's ``columns:`` decides which fields render, in which order, and how
wide; ``page_size:`` decides how many rows one page fetches and whether a pager
shows. A list surface's ``field`` lines carry the same ``width:`` hint and take
the same ``page_size:``. Only a live app proves the whole path — parse → route
builder → fetch → render — so this boots a copy of ``fixtures/scope_runtime``
with a 40-row ``Stack`` entity appended and reads the region and the list rows
as the admin.

The copy lives in ``tmp_path``, so no ``xdist_group`` pin is needed.
"""

from __future__ import annotations

import os
import re
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "scope_runtime"
_BASE_URL = "http://scope-runtime.local"
_PASSWORD = "list-columns-password"  # nosec B105 — disposable scratch DB only
_ADMIN = "admin@scope.test"
_ROWS = 40

_STACK_DSL = """

entity Stack "Stack":
  id: uuid pk
  title: str(200) required
  status: enum[draft, marked]=draft
  photo_url: str(500)
  department: ref Department required

  permit:
    read: role(admin)
    list: role(admin)

  scope:
    read: all
      as: admin
    list: all
      as: admin


surface stack_list "Stacks":
  uses entity Stack
  mode: list
  page_size: 25
  section main:
    field title "Title" width: 34%
    field department "Department"
    field status "Status"


workspace stack_desk "Stack Desk":
  purpose: "Every stack, title first"
  access: persona(admin)

  stacks:
    source: Stack
    display: list
    sort: title asc
    columns: title(width: 34%), photo_url, status
    page_size: 25
"""

_TITLE_CELL = re.compile(r">Stack \d\d<")


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "scope_runtime_list_columns"
    shutil.copytree(_FIXTURE, root)
    domain = root / "dsl" / "domain.dsl"
    domain.write_text(domain.read_text() + _STACK_DSL)
    return root


def _insert(conn: Any, table: str, row: dict[str, Any]) -> None:
    """Table/column names are hardcoded DSL constants; values are parameterised."""
    cols = ", ".join(f'"{k}"' for k in row)
    placeholders = ", ".join("%s" for _ in row)
    conn.execute(  # nosemgrep — constant identifiers, param values
        f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders})', list(row.values())
    )


class _App:
    def __init__(self, transport: Any, db_url: str) -> None:
        self.transport = transport
        self.db_url = db_url


def _seed(app: _App, auth_store: Any) -> None:
    import psycopg

    if auth_store.get_user_by_email(_ADMIN) is None:
        auth_store.create_user(_ADMIN, _PASSWORD, roles=["admin"])
    dept = str(uuid.uuid4())
    with psycopg.connect(app.db_url) as conn:
        _insert(conn, "Department", {"id": dept, "name": "English"})
        for i in range(_ROWS):
            _insert(
                conn,
                "Stack",
                {
                    "id": str(uuid.uuid4()),
                    "title": f"Stack {i:02d}",
                    "status": "draft",
                    "photo_url": "",
                    "department": dept,
                },
            )
        conn.commit()


@pytest.fixture
async def app(tmp_path: Path) -> AsyncIterator[_App]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL")

    import httpx

    from dazzle.rbac.verifier import _build_asgi_app, _DisposableDatabase, _probe_transport

    async with _DisposableDatabase(_PG_URL) as db_url:
        built = _build_asgi_app(_project(tmp_path), db_url)
        auth_store = built.builder.auth_store
        assert auth_store is not None, "scope_runtime has auth enabled"
        a = _App(_probe_transport(httpx.ASGITransport(app=built.app)), db_url)
        _seed(a, auth_store)
        try:
            yield a
        finally:
            db_manager = getattr(built.builder, "_db_manager", None)
            if db_manager is not None:
                db_manager.close_pool()


async def _get(app: _App, path: str, headers: dict[str, str] | None = None, **params: str) -> str:
    import httpx

    from dazzle.cli.rbac import _login

    async with httpx.AsyncClient(
        transport=app.transport, base_url=_BASE_URL, follow_redirects=True
    ) as client:
        await _login(client, _BASE_URL, _ADMIN, _PASSWORD)
        resp = await client.get(path, params=params, headers=headers or {})
    assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text[:400]}"
    return resp.text


async def test_region_columns_and_page_size(app: _App) -> None:
    body = await _get(app, "/api/workspaces/stack_desk/regions/stacks")

    # columns: only the named fields, in the authored order — the image field
    # is named, so it shows on a list; the unnamed ref column does not.
    heads = re.findall(r"<th>([^<]*)</th>", body)
    assert heads == ["Title", "Photo Url", "Status"], heads
    assert '<col data-dz-col="title" style="width: 34%">' in body
    # page_size: 25 → one page of 25 rows and a pager over the 40 matches.
    assert len(_TITLE_CELL.findall(body)) == 25
    assert "data-dz-pagination" in body
    assert "page=2&amp;page_size=25" in body

    page_two = await _get(
        app, "/api/workspaces/stack_desk/regions/stacks", page="2", page_size="25"
    )
    assert len(_TITLE_CELL.findall(page_two)) == _ROWS - 25


async def test_list_rows_window_to_the_declared_page_size(app: _App) -> None:
    # The list page bakes `page_size=25` into the tbody fetch and the grid's
    # refresh carrier (pinned in tests/unit/test_list_columns_1792.py); this is
    # the row endpoint answering that fetch: 25 rows and a pager over 40.
    rows = await _get(
        app,
        "/stacks",
        headers={"HX-Request": "true", "HX-Target": "stack_list-body", "Accept": "text/html"},
        page_size="25",
    )
    assert len(_TITLE_CELL.findall(rows)) == 25
    assert 'data-dz-grid-goto="2"' in rows, "pager over 40 rows at 25 per page"
