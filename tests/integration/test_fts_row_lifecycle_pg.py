"""Real-Postgres proof that full-text search hides the rows the list hides (ship AA).

``Repository.list`` adds ``deleted_at IS NULL`` for a ``soft_delete`` entity and
``<end_field> IS NULL`` for a ``temporal:`` entity; before flense ship AA
``Repository.fts_search`` added neither, so ``GET /_dazzle/fts/{entity}`` returned
soft-deleted and ended rows. Both now go through ``Repository._row_lifecycle_filters``.

This boots a copy of ``fixtures/scope_runtime`` with two searchable entities added
(``Memo`` is ``soft_delete``, ``Posting`` is ``temporal:``), seeds a live and a
hidden row of each matching the same term, and checks that the hidden rows match
the raw ``search_vector`` query but are absent from the admin's FTS results.

The copy lives in ``tmp_path``, so no ``xdist_group`` pin is needed.
"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "scope_runtime"
_BASE_URL = "http://scope-runtime.local"
_PASSWORD = "fts-lifecycle-password"  # nosec B105 — disposable scratch DB only
_ADMIN = "admin@scope.test"

_LIFECYCLE_DSL = """

entity Memo "Memo":
  id: uuid pk
  title: str(200) required
  soft_delete

  permit:
    read: role(admin)
    list: role(admin)

  scope:
    read: all
      as: admin
    list: all
      as: admin


entity Posting "Posting":
  id: uuid pk
  title: str(200) required
  started_at: date required
  ended_at: date

  temporal:
    start_field: started_at
    end_field: ended_at
    key_field: id

  permit:
    read: role(admin)
    list: role(admin)

  scope:
    read: all
      as: admin
    list: all
      as: admin


search on Memo:
  fields: title
  tokenizer: english

search on Posting:
  fields: title
  tokenizer: english
"""


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "scope_runtime_fts_lifecycle"
    shutil.copytree(_FIXTURE, root)
    domain = root / "dsl" / "domain.dsl"
    domain.write_text(domain.read_text() + _LIFECYCLE_DSL)
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
        self.live_memo = str(uuid.uuid4())
        self.deleted_memo = str(uuid.uuid4())
        self.active_posting = str(uuid.uuid4())
        self.ended_posting = str(uuid.uuid4())

    def raw_matches(self, table: str) -> set[str]:
        """Ids matching the term with no lifecycle filter — what search used to see."""
        import psycopg

        with psycopg.connect(self.db_url) as conn:
            rows = conn.execute(  # nosemgrep — constant identifier
                f'SELECT "id" FROM "{table}" '
                "WHERE search_vector @@ websearch_to_tsquery('english', %s)",
                ["quarterly"],
            ).fetchall()
        return {str(r[0]) for r in rows}


def _seed(app: _App, auth_store: Any) -> None:
    import psycopg

    if auth_store.get_user_by_email(_ADMIN) is None:
        auth_store.create_user(_ADMIN, _PASSWORD, roles=["admin"])
    with psycopg.connect(app.db_url) as conn:
        _insert(conn, "Memo", {"id": app.live_memo, "title": "Quarterly memo"})
        _insert(
            conn,
            "Memo",
            {
                "id": app.deleted_memo,
                "title": "Quarterly memo (withdrawn)",
                "deleted_at": datetime.now(UTC),
            },
        )
        _insert(
            conn,
            "Posting",
            {
                "id": app.active_posting,
                "title": "Quarterly posting",
                "started_at": date(2026, 1, 1),
            },
        )
        _insert(
            conn,
            "Posting",
            {
                "id": app.ended_posting,
                "title": "Quarterly posting (closed)",
                "started_at": date(2025, 1, 1),
                "ended_at": date(2025, 6, 30),
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


async def _fts_ids(app: _App, entity: str) -> set[str]:
    import httpx

    from dazzle.cli.rbac import _login

    async with httpx.AsyncClient(
        transport=app.transport, base_url=_BASE_URL, follow_redirects=True
    ) as client:
        await _login(client, _BASE_URL, _ADMIN, _PASSWORD)
        resp = await client.get(f"/_dazzle/fts/{entity}", params={"q": "quarterly"})
    assert resp.status_code == 200, f"{entity} FTS: {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    ids = {str(row["id"]) for row in body["items"]}
    assert body["total"] == len(ids), "total must count only visible rows"
    return ids


@pytest.mark.parametrize(
    ("entity", "visible", "hidden"),
    [
        ("Memo", "live_memo", "deleted_memo"),
        ("Posting", "active_posting", "ended_posting"),
    ],
)
async def test_fts_hides_rows_the_list_hides(
    app: _App, entity: str, visible: str, hidden: str
) -> None:
    shown, hidden_id = getattr(app, visible), getattr(app, hidden)
    assert app.raw_matches(entity) == {shown, hidden_id}, "both rows match the raw query"
    assert await _fts_ids(app, entity) == {shown}
