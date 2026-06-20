"""Unit test for the 0006 is_test migration — runs against an in-memory SQLite
DB to exercise the dialect-agnostic upgrade/downgrade paths without a live
Postgres. (Real-PG behaviour is covered by tests/integration/test_tenant_is_test_pg.py.)"""

from __future__ import annotations

import importlib.util
import types
from collections.abc import Callable
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect as sa_inspect

_MIGRATION = (
    Path(__file__).resolve().parents[2] / "src/dazzle/http/alembic/versions/0006_tenant_is_test.py"
)


def _load_migration() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("mig_0006", _MIGRATION)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(callback: Callable[[sa.engine.Connection], None]) -> None:
    engine = sa.create_engine("sqlite://")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            callback(conn)
        conn.commit()


def test_upgrade_no_op_when_tenants_absent() -> None:
    mod = _load_migration()
    # No `tenants` table at all → upgrade must be a no-op, not an error.
    _run(lambda conn: mod.upgrade())


def test_upgrade_adds_is_test_to_existing_table() -> None:
    mod = _load_migration()

    def body(conn):
        conn.execute(sa.text("CREATE TABLE tenants (id TEXT PRIMARY KEY, slug TEXT)"))
        conn.execute(sa.text("INSERT INTO tenants (id, slug) VALUES ('1', 'acme')"))
        mod.upgrade()
        cols = {c["name"] for c in sa_inspect(conn).get_columns("tenants")}
        assert "is_test" in cols
        # existing row defaults to false (0 in SQLite)
        val = conn.execute(sa.text("SELECT is_test FROM tenants WHERE id='1'")).scalar()
        assert val in (0, False)

    _run(body)


def test_upgrade_idempotent_when_column_present() -> None:
    mod = _load_migration()

    def body(conn):
        conn.execute(
            sa.text(
                "CREATE TABLE tenants (id TEXT PRIMARY KEY, is_test BOOLEAN NOT NULL DEFAULT 0)"
            )
        )
        mod.upgrade()  # column already present → no-op, no error
        cols = {c["name"] for c in sa_inspect(conn).get_columns("tenants")}
        assert "is_test" in cols

    _run(body)
