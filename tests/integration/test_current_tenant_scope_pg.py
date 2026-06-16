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


_HIER_DSL = """module t
app t "T"
persona viewer "Viewer":
  capabilities: [read]
entity Trust "Trust":
  id: uuid pk
  slug: slug required
  tenant_host:
    domain: app.example
    slug_field: slug
    order: 1
entity School "School":
  id: uuid pk
  slug: slug required
  trust: ref Trust required
  tenant_host:
    domain: app.example
    slug_field: slug
    parent: trust
    order: 2
entity Doc "Doc":
  id: uuid pk
  title: str(80) required
  school: ref School required
  permit:
    read: role(viewer)
    update: role(viewer)
  scope:
    read: school = current_tenant
      as: viewer
    update: school = current_tenant
      as: viewer
"""


def _compile_doc_scope(op_suffix: str, schema: str) -> str:
    """Build the appspec and compile Doc's READ/UPDATE current_tenant scope to a
    policy-mode WHERE body (the REAL compiler output) for the given scratch schema."""
    import tempfile
    from pathlib import Path

    from dazzle.back.runtime.predicate_compiler import compile_predicate_policy
    from dazzle.core.ir.fk_graph import FKGraph
    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules

    d = Path(tempfile.mkdtemp()) / "h.dsl"
    d.write_text(_HIER_DSL)
    appspec = build_appspec(parse_modules([d]), "t")
    fk = FKGraph.from_entities(list(appspec.domain.entities))
    doc = next(e for e in appspec.domain.entities if e.name == "Doc")
    rule = next(s for s in doc.access.scopes if str(s.operation).endswith(op_suffix))
    return compile_predicate_policy(
        rule.predicate, "Doc", fk, entity_types=lambda e, f: "uuid", schema=schema
    )


@pytest.mark.skipif(not _PG_URL, reason="no TEST_DATABASE_URL / DATABASE_URL — needs real Postgres")
def test_current_tenant_hierarchy_aggregate_vs_single() -> None:
    """ADR-0036 Layer 2 — the compiled self-or-ancestor disjunction isolates
    correctly against real Postgres: single at a leaf (School) host, aggregate at
    an ancestor (Trust) host, NO cross-trust bleed, and fail-closed when unbound.
    Drives the REAL compiler output, not a hand-written WHERE.
    """
    import psycopg

    from dazzle.back.runtime.pg_backend import _set_host_tenant_context

    schema = f"_cth_{uuid.uuid4().hex[:8]}"
    read_where = _compile_doc_scope("read", schema)
    update_where = _compile_doc_scope("update", schema)

    trust_a, trust_b = str(uuid.uuid4()), str(uuid.uuid4())
    school_a1, school_a2, school_b1 = (str(uuid.uuid4()) for _ in range(3))

    def _q(sql: str) -> str:
        return sql  # readability helper

    with psycopg.connect(_PG_URL, autocommit=True) as setup:
        for stmt in (
            f'CREATE SCHEMA "{schema}"',
            f'CREATE TABLE "{schema}"."Trust" (id uuid primary key, slug text not null)',
            f'CREATE TABLE "{schema}"."School" (id uuid primary key, slug text not null, trust uuid not null)',
            f'CREATE TABLE "{schema}"."Doc" (id uuid primary key, title text not null, school uuid not null)',
        ):
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            setup.execute(stmt)
        for tid in (trust_a, trust_b):
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            setup.execute(
                f'INSERT INTO "{schema}"."Trust" (id, slug) VALUES (%s, %s)', [tid, tid[:8]]
            )
        for sid, tid in ((school_a1, trust_a), (school_a2, trust_a), (school_b1, trust_b)):
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            setup.execute(
                f'INSERT INTO "{schema}"."School" (id, slug, trust) VALUES (%s, %s, %s)',
                [sid, sid[:8], tid],
            )
        # Docs: 2 in A1, 1 in A2, 1 in B1.
        for sid, n in ((school_a1, 2), (school_a2, 1), (school_b1, 1)):
            for _ in range(n):
                # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                setup.execute(
                    f'INSERT INTO "{schema}"."Doc" (id, title, school) VALUES (%s, %s, %s)',
                    [str(uuid.uuid4()), "doc", sid],
                )

    read_sql = f'SELECT count(*)::int FROM "{schema}"."Doc" AS "Doc" WHERE {read_where}'
    update_sql = f'SELECT count(*)::int FROM "{schema}"."Doc" AS "Doc" WHERE {update_where}'

    def _count(conn, sql, host):  # type: ignore[no-untyped-def]
        with conn.transaction():
            _set_host_tenant_context(conn, host)
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            return conn.execute(sql).fetchone()[0]

    try:
        conn = psycopg.connect(_PG_URL)
        try:
            # READ — single at a leaf (School) host:
            assert _count(conn, read_sql, school_a1) == 2  # School A1's two docs
            assert _count(conn, read_sql, school_a2) == 1
            assert _count(conn, read_sql, school_b1) == 1
            # READ — aggregate at an ancestor (Trust) host:
            assert _count(conn, read_sql, trust_a) == 3  # A1(2) + A2(1), across the trust
            assert _count(conn, read_sql, trust_b) == 1  # B1(1) — NO bleed from trust A
            # READ — deny: unrelated id, unset, empty-string → fail-closed zero.
            assert _count(conn, read_sql, str(uuid.uuid4())) == 0
            assert _count(conn, read_sql, None) == 0
            with conn.transaction():
                conn.execute("SELECT set_config('dazzle.host_tenant_id', '', true)")
                assert conn.execute(read_sql).fetchone()[0] == 0

            # WRITE (UPDATE) — single only: a Trust (ancestor) host matches NOTHING
            # (read-only aggregate); a School (leaf) host matches its own rows.
            assert _count(conn, update_sql, school_a1) == 2
            assert _count(conn, update_sql, trust_a) == 0  # aggregate host is read-only
        finally:
            conn.close()
    finally:
        with psycopg.connect(_PG_URL, autocommit=True) as teardown:
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            teardown.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
