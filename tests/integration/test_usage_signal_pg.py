"""Real-PostgreSQL proof of the usage-signal capture table (ADR-0050 Phase 1).

Marked e2e + postgres: skipped without TEST_DATABASE_URL/DATABASE_URL.
Mirrors tests/integration/test_auth_activation_pg.py's scratch-DB harness.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def scratch_conn() -> Iterator[psycopg.Connection]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin_url = _admin_url()
    base, _, _old = admin_url.rpartition("/")
    scratch = f"dazzle_usage_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep — uuid-derived
    try:
        with psycopg.connect(f"{base}/{scratch}") as conn:
            yield conn
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (scratch,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


def test_ensure_usage_events_table_creates_shape_and_is_idempotent(
    scratch_conn: psycopg.Connection,
) -> None:
    from dazzle.http.runtime.usage_signal import ensure_usage_events_table

    with scratch_conn.cursor() as cur:
        ensure_usage_events_table(cur)
        ensure_usage_events_table(cur)  # idempotent — second call must not raise
    scratch_conn.commit()

    with scratch_conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = '_dazzle_usage_events' ORDER BY column_name"
        )
        cols = {r[0] for r in cur.fetchall()}
    assert cols == {"id", "tenant_id", "surface", "kind", "target", "ts"}


def test_usage_events_insert_and_tenant_fenced_readback(
    scratch_conn: psycopg.Connection,
) -> None:
    from dazzle.http.runtime.usage_signal import (
        USAGE_KIND_ACTION,
        USAGE_KIND_FIELD,
        ensure_usage_events_table,
    )

    with scratch_conn.cursor() as cur:
        ensure_usage_events_table(cur)
        # Two tenants, overlapping (surface, target) — a fenced read must not mix them.
        for tenant, kind, target, n in [
            ("t-a", USAGE_KIND_ACTION, "approve", 3),
            ("t-a", USAGE_KIND_FIELD, "title", 2),
            ("t-b", USAGE_KIND_ACTION, "approve", 5),
        ]:
            for _ in range(n):
                cur.execute(
                    "INSERT INTO _dazzle_usage_events (tenant_id, surface, kind, target) "
                    "VALUES (%s, %s, %s, %s)",
                    (tenant, "orders", kind, target),
                )
    scratch_conn.commit()

    with scratch_conn.cursor() as cur:
        cur.execute(
            "SELECT kind, target, count(*) FROM _dazzle_usage_events "
            "WHERE tenant_id = %s AND surface = %s GROUP BY kind, target ORDER BY target",
            ("t-a", "orders"),
        )
        rows = {(k, t): c for k, t, c in cur.fetchall()}
    assert rows == {(USAGE_KIND_ACTION, "approve"): 3, (USAGE_KIND_FIELD, "title"): 2}
