# tests/unit/test_grant_store.py
"""Tests for runtime grant store (PostgreSQL)."""

import os
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from dazzle_back.runtime.grant_store import GrantStore


@pytest.fixture(scope="session")
def pg_grant_conn_factory():
    """Session-scoped factory for PostgreSQL connections. Skips if no TEST_DATABASE_URL."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set — skipping PostgreSQL grant tests")

    def factory():
        return psycopg.connect(url, row_factory=dict_row)

    return factory


@pytest.fixture
def pg_conn(pg_grant_conn_factory):
    """Per-test connection that drops grant tables for clean state."""
    conn = pg_grant_conn_factory()
    conn.execute("DROP TABLE IF EXISTS _grant_events, _grants")
    conn.commit()
    yield conn
    conn.close()


class TestPgConnectivity:
    def test_connection_works(self, pg_conn):
        row = pg_conn.execute("SELECT 1 AS ok").fetchone()
        assert row["ok"] == 1


class TestGrantStoreInit:
    def test_tables_created(self, pg_conn):
        GrantStore(pg_conn)
        row = pg_conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE '_grant%'"
        ).fetchall()
        tables = {r["tablename"] for r in row}
        assert "_grants" in tables
        assert "_grant_events" in tables

    def test_check_constraint_on_status(self, pg_conn):
        GrantStore(pg_conn)
        from psycopg import errors

        with pytest.raises(errors.CheckViolation):
            pg_conn.execute(
                """INSERT INTO _grants (id, schema_name, relation, principal_id, scope_entity,
                   scope_id, status, granted_by_id, granted_at)
                   VALUES (gen_random_uuid(), 'x', 'r', gen_random_uuid(), 'E',
                   gen_random_uuid(), 'INVALID_STATUS', gen_random_uuid(), now())"""
            )
        pg_conn.rollback()

    def test_check_constraint_on_event_type(self, pg_conn):
        GrantStore(pg_conn)
        grant_id = uuid4()
        pg_conn.execute(
            """INSERT INTO _grants (id, schema_name, relation, principal_id, scope_entity,
               scope_id, status, granted_by_id, granted_at)
               VALUES (%s, 'x', 'r', %s, 'E', %s, 'active', %s, now())""",
            (grant_id, uuid4(), uuid4(), uuid4()),
        )
        from psycopg import errors

        with pytest.raises(errors.CheckViolation):
            pg_conn.execute(
                """INSERT INTO _grant_events (id, grant_id, event_type, actor_id, timestamp)
                   VALUES (gen_random_uuid(), %s, 'INVALID_EVENT', gen_random_uuid(), now())""",
                (grant_id,),
            )
        pg_conn.rollback()
