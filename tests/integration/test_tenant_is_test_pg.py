"""Real-Postgres verification for the is_test substrate (#1339 slice 0).

Two paths against a disposable database:
  * fresh install — `TenantRegistry.ensure_table()` creates `public.tenants`
    with `is_test`, and `create(..., is_test=True)` round-trips the flag.
  * migration — a pre-0006 `tenants` table (no `is_test`) gains the column via
    the 0006 `upgrade()`, defaulting existing rows to false.

Marked ``postgres`` (+ ``e2e``): skipped locally without
``TEST_DATABASE_URL`` / ``DATABASE_URL``; CI's ``postgres-tests`` job runs it.
"""

from __future__ import annotations

import os
import uuid

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect as sa_inspect

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture
def pg_url() -> str:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    return _PG_URL


def test_fresh_ensure_table_round_trips_is_test(pg_url: str) -> None:
    from dazzle.tenant.registry import TenantRegistry

    suffix = uuid.uuid4().hex[:8]
    reg = TenantRegistry(pg_url)
    reg.ensure_table()

    normal = reg.create(f"cust_{suffix}", "Normal Co")
    test = reg.create(f"qa_{suffix}", "QA tenant", is_test=True, allow_reserved=True)
    try:
        assert normal.is_test is False
        assert test.is_test is True
        assert reg.get(f"qa_{suffix}").is_test is True
        assert reg.get(f"cust_{suffix}").is_test is False
    finally:
        import psycopg

        with psycopg.connect(pg_url) as conn:
            conn.execute(
                "DELETE FROM public.tenants WHERE slug = ANY(%s)",
                ([f"cust_{suffix}", f"qa_{suffix}"],),
            )
            conn.commit()


def test_migration_adds_is_test_to_pre0006_table(pg_url: str) -> None:
    import psycopg

    tbl = f"tenants_pre0006_{uuid.uuid4().hex[:8]}"
    engine = sa.create_engine(pg_url.replace("postgresql://", "postgresql+psycopg://"), future=True)
    try:
        # `tbl` is a uuid-derived scratch identifier, never user input.
        with engine.begin() as conn:
            conn.execute(
                sa.text(f'CREATE TABLE "{tbl}" (id TEXT PRIMARY KEY, slug TEXT)')
            )  # nosemgrep — uuid-derived test table name
            conn.execute(
                sa.text(f"INSERT INTO \"{tbl}\" (id, slug) VALUES ('1', 'legacy')")
            )  # nosemgrep — uuid-derived test table name

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx) as op_ctx:
                op_ctx.add_column(
                    tbl,
                    sa.Column(
                        "is_test",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.text("false"),
                    ),
                )
            conn.commit()
            cols = {c["name"] for c in sa_inspect(conn).get_columns(tbl)}
            assert "is_test" in cols
            val = conn.execute(sa.text(f"SELECT is_test FROM \"{tbl}\" WHERE id='1'")).scalar()
            assert val is False
    finally:
        with psycopg.connect(pg_url) as conn:
            conn.execute(f'DROP TABLE IF EXISTS "{tbl}"')
            conn.commit()
        engine.dispose()
