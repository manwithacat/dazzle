"""#1394 — real-Postgres proof of the `current_tenant` scope GUC round-trip.

The security property: a `field = current_tenant` scope predicate, compiled in
policy mode, filters rows to the host-resolved tenant via the dedicated
``dazzle.host_tenant_id`` GUC — and fails CLOSED (zero rows) when no host tenant
is bound. This drives a real psycopg connection so the GUC set_config →
current_setting round-trip and the ``::uuid`` cast are exercised against actual
Postgres, not a fake.

It exercises the real runtime code paths:
  * ``pg_backend._set_host_tenant_context`` — the set_config the lease emits.
  * ``predicate_compiler._guc_read_host_tenant`` — the policy-body GUC read.

Marked ``postgres`` (+ ``e2e``): skipped locally without ``TEST_DATABASE_URL`` /
``DATABASE_URL``; CI's ``postgres-tests`` job runs it against a real ``postgres:16``.
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.mark.skipif(not _PG_URL, reason="no TEST_DATABASE_URL / DATABASE_URL — needs real Postgres")
def test_current_tenant_guc_filters_and_fails_closed() -> None:
    import psycopg

    from dazzle.back.runtime.pg_backend import _set_host_tenant_context
    from dazzle.back.runtime.predicate_compiler import _guc_read_host_tenant

    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())
    table = f"_ct_scope_test_{uuid.uuid4().hex[:8]}"
    qtable = f'"{table}"'

    # `qtable` is a server-generated identifier, not user input — same nosemgrep
    # pair the other PG integration tests use for scratch-DB DDL.
    create_sql = f"CREATE TABLE {qtable} (id uuid primary key, org uuid not null)"
    insert_sql = f"INSERT INTO {qtable} (id, org) VALUES (%s, %s)"
    # The policy-body shape the compiler emits for `org = current_tenant`.
    where = f"org = {_guc_read_host_tenant('uuid')}"
    select_sql = f"SELECT count(*)::int AS n FROM {qtable} WHERE {where}"

    with psycopg.connect(_PG_URL, autocommit=True) as setup:
        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        setup.execute(create_sql)
        for org in (tenant_a, tenant_a, tenant_b):  # 2 rows for A, 1 for B
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            setup.execute(insert_sql, [str(uuid.uuid4()), org])

    try:
        conn = psycopg.connect(_PG_URL)
        try:
            # (1) Bind host tenant A via the REAL runtime helper, then run the
            #     compiled policy-body filter → exactly tenant A's 2 rows.
            with conn.transaction():
                _set_host_tenant_context(conn, tenant_a)
                # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                cur = conn.execute(select_sql)
                assert cur.fetchone()[0] == 2

            # (2) Bind host tenant B → tenant B's single row (no A bleed-through).
            with conn.transaction():
                _set_host_tenant_context(conn, tenant_b)
                # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                cur = conn.execute(select_sql)
                assert cur.fetchone()[0] == 1

            # (3) FAIL CLOSED — unset: no host tenant bound (None → no set_config)
            #     → the GUC reads NULL → `org = NULL` matches nothing. Zero rows,
            #     never the whole table.
            with conn.transaction():
                _set_host_tenant_context(conn, None)
                # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                cur = conn.execute(select_sql)
                assert cur.fetchone()[0] == 0

            # (4) FAIL CLOSED — empty string: a pooled connection whose GUC was
            #     SET LOCAL by a prior request reverts the placeholder to ''. The
            #     NULLIF wrapper must collapse '' → NULL → deny, NOT raise on
            #     `''::uuid`. This is the case the bare cast got wrong.
            with conn.transaction():
                conn.execute("SELECT set_config('dazzle.host_tenant_id', '', true)")
                # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                cur = conn.execute(select_sql)
                assert cur.fetchone()[0] == 0
        finally:
            conn.close()
    finally:
        with psycopg.connect(_PG_URL, autocommit=True) as teardown:
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            teardown.execute(f"DROP TABLE IF EXISTS {qtable}")
