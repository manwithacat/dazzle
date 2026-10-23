"""Real-PostgreSQL proof of the `search:` column apply + drift chain (#1850).

``dazzle db upgrade`` / ``dazzle db apply-search`` reconcile the DSL ``search:``
columns after the migrations because production boots run no DDL. On one scratch
database (dropped in ``finally``) this drives the async apply and drift functions
over the real ``dazzle.db.connection.get_connection`` factory the CLI uses:

1. a missing column + GIN index are created, and ``detect_search_drift`` is then
   empty;
2. a second apply runs no DDL;
3. a changed ``search:`` field list is reported as drift and rebuilds the column
   (new expression) and index;
4. a removed ``search:`` block drops the stale generated column.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import psycopg
import pytest

from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.search import SearchField, SearchSpec

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

_DOC = SimpleNamespace(
    name="Doc",
    fields=[
        FieldSpec(name="id", type=FieldType(kind=FieldTypeKind.UUID)),
        FieldSpec(name="title", type=FieldType(kind=FieldTypeKind.STR)),
        FieldSpec(name="body", type=FieldType(kind=FieldTypeKind.TEXT)),
    ],
)


def _appspec(*fields: tuple[str, int]) -> Any:
    searches = (
        [SearchSpec(entity="Doc", fields=[SearchField(path=p, weight=w) for p, w in fields])]
        if fields
        else []
    )
    return SimpleNamespace(searches=searches)


@pytest.fixture
def scratch_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _PG_URL.replace("postgresql+psycopg://", "postgresql://")
    base, _, _ = admin.rpartition("/")
    name = f"dazzle_search_apply_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{name}"')  # nosemgrep — uuid-derived db name
    url = f"{base}/{name}"
    try:
        with psycopg.connect(url, autocommit=True) as c:
            c.execute('CREATE TABLE "Doc" (id uuid PRIMARY KEY, title text, body text)')
        yield url
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()",
                (name,),
            )
            a.execute(f'DROP DATABASE IF EXISTS "{name}"')  # nosemgrep


def _run(url: str, fn: Any, appspec: Any) -> Any:
    from dazzle.db.connection import get_connection

    async def _go() -> Any:
        conn = await get_connection(explicit_url=url)
        try:
            return await fn(conn, appspec, [_DOC])
        finally:
            await conn.close()

    return asyncio.run(_go())


def _live(url: str) -> tuple[str | None, bool]:
    with psycopg.connect(url) as c:
        row = c.execute(
            "SELECT generation_expression FROM information_schema.columns "
            "WHERE table_name = 'Doc' AND column_name = 'search_vector'"
        ).fetchone()
        has_index = c.execute(
            "SELECT 1 FROM pg_indexes WHERE indexname = 'ix_doc_search_vector'"
        ).fetchone()
    return (row[0] if row else None), has_index is not None


def test_apply_is_idempotent_and_rebuilds_on_a_changed_field_list(scratch_url: str) -> None:
    from dazzle.db.search_apply import apply_search_columns, detect_search_drift

    v1 = _appspec(("title", 4), ("body", 1))
    assert [d["action"] for d in _run(scratch_url, detect_search_drift, v1)] == ["create"]

    actions = _run(scratch_url, apply_search_columns, v1)
    assert [a.action for a in actions] == ["create"]
    expr, has_index = _live(scratch_url)
    assert expr is not None and "'A'" in expr and "'D'" in expr
    assert has_index
    assert _run(scratch_url, detect_search_drift, v1) == []

    # Re-run: no DDL at all.
    assert _run(scratch_url, apply_search_columns, v1) == []

    # body's weight moves 1 → 3 (D → B): drift, then a rebuild.
    v2 = _appspec(("title", 4), ("body", 3))
    assert [d["action"] for d in _run(scratch_url, detect_search_drift, v2)] == ["rebuild"]
    assert [a.action for a in _run(scratch_url, apply_search_columns, v2)] == ["rebuild"]
    expr, has_index = _live(scratch_url)
    assert expr is not None and "'B'" in expr and "'D'" not in expr
    assert has_index
    assert _run(scratch_url, detect_search_drift, v2) == []

    # The index alone dropped: only the index is re-created.
    with psycopg.connect(scratch_url, autocommit=True) as c:
        c.execute("DROP INDEX ix_doc_search_vector")
    assert [a.action for a in _run(scratch_url, apply_search_columns, v2)] == ["add_index"]
    assert _live(scratch_url)[1]

    # The search: block removed: the stale generated column goes.
    v0 = _appspec()
    assert [a.action for a in _run(scratch_url, apply_search_columns, v0)] == ["drop_stale"]
    assert _live(scratch_url) == (None, False)
    assert _run(scratch_url, detect_search_drift, v0) == []
