"""Real-Postgres proof of the region presentation options (#1809, #1814).

* ``filters: none`` — a list region renders no filter/search bar.
* ``exclude: <region>`` — the region omits the rows the named sibling shows on
  its first page, in the same one scope-safe query (``id NOT IN (<sibling's
  first-page id query>)``), so the matched total shrinks with it.
* ``limit:`` on ``display: comparison`` — top-N *after* ranking, cut in the one
  grouped aggregate SQL (ORDER BY the ranking measure, LIMIT N).

Only a live app proves the whole path — parse → route builder → fetch → render —
so this boots a copy of ``fixtures/scope_runtime`` with a nine-row ``Stack``
entity appended and reads the regions as the admin. The copy lives in
``tmp_path``, so no ``xdist_group`` pin is needed.
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
_PASSWORD = "region-options-password"  # nosec B105 — disposable scratch DB only
_ADMIN = "admin@scope.test"

# Alpha owns 1 stack, Beta 5, Gamma 3 — label order (Alpha, Beta, Gamma) differs
# from rank order (Beta, Gamma, Alpha), so a LIMIT without ORDER BY the measure
# would keep the wrong buckets.
_DEPARTMENTS = {"Alpha": 1, "Beta": 5, "Gamma": 3}

_STACK_DSL = """

entity Stack "Stack":
  id: uuid pk
  title: str(200) required
  status: enum[draft, marked]=draft
  department: ref Department required

  permit:
    read: role(admin)
    list: role(admin)

  scope:
    read: all
      as: admin
    list: all
      as: admin


workspace stack_desk "Stack Desk":
  purpose: "Resume the first stack, then the rest"
  access: persona(admin)

  resume:
    source: Stack
    display: list
    sort: title asc
    limit: 1
    filters: none

  recent:
    source: Stack
    display: list
    sort: title asc
    limit: 5
    filters: none
    exclude: resume

  everything:
    source: Stack
    display: list
    sort: title asc
    limit: 3

  busiest:
    source: Stack
    display: comparison
    group_by: department
    aggregate:
      stacks: count(Stack)
    rank_by: stacks
    order: desc
    limit: 2
    eager: true
"""

_TITLE_CELL = re.compile(r">Stack (\d\d)<")


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "scope_runtime_region_options"
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
    with psycopg.connect(app.db_url) as conn:
        n = 0
        for name, count in _DEPARTMENTS.items():
            dept = str(uuid.uuid4())
            _insert(conn, "Department", {"id": dept, "name": name})
            for _ in range(count):
                _insert(
                    conn,
                    "Stack",
                    {
                        "id": str(uuid.uuid4()),
                        "title": f"Stack {n:02d}",
                        "status": "draft",
                        "department": dept,
                    },
                )
                n += 1
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


async def _get(app: _App, path: str) -> str:
    import httpx

    from dazzle.cli.rbac import _login

    async with httpx.AsyncClient(
        transport=app.transport, base_url=_BASE_URL, follow_redirects=True
    ) as client:
        await _login(client, _BASE_URL, _ADMIN, _PASSWORD)
        resp = await client.get(path)
    assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text[:400]}"
    return resp.text


def _titles(body: str) -> list[str]:
    return _TITLE_CELL.findall(body)


async def test_exclude_omits_the_siblings_first_page(app: _App) -> None:
    resume = await _get(app, "/api/workspaces/stack_desk/regions/resume")
    recent = await _get(app, "/api/workspaces/stack_desk/regions/recent")

    assert _titles(resume) == ["00"]
    # Without `exclude:` this would be 00..04; the resume row is left out and
    # the five rows after it fill the page.
    assert _titles(recent) == ["01", "02", "03", "04", "05"]


async def test_filters_none_hides_the_filter_bar(app: _App) -> None:
    hidden = await _get(app, "/api/workspaces/stack_desk/regions/recent")
    shown = await _get(app, "/api/workspaces/stack_desk/regions/everything")

    assert "filter-bar" not in hidden
    assert "filter-bar" in shown, "an unmarked list region keeps its filter bar"


async def test_comparison_limit_keeps_the_top_n_after_ranking(app: _App) -> None:
    body = await _get(app, "/api/workspaces/stack_desk/regions/busiest")

    # Beta (5) and Gamma (3) rank first; Alpha (1) sorts first by label but is
    # cut. The LIMIT runs in the grouped SQL, after ORDER BY the measure.
    assert "Beta" in body and "Gamma" in body
    assert "Alpha" not in body
