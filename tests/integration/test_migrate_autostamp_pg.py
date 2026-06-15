"""#1390 — real-Postgres proof of the empty-`alembic_version` auto-stamp reconciliation.

When the schema is already materialized (the app booted, creating
``_dazzle_params`` + DSL tables) but ``alembic_version`` is empty, ``dazzle
migrate`` / ``dazzle db migrate`` would replay the baseline chain (CREATE TABLE
on existing tables) and refuse a simple additive diff. The fix reconciles by
stamping to heads first — but ONLY when the schema is genuinely materialized, so
a fresh DB still gets its baseline.

This drives a disposable Postgres database so the introspection + stamp round-trip
runs against real Postgres, not a fake. Marked ``postgres`` (+ ``e2e``).
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _libpq_url(database: str) -> str:
    """A psycopg.connect()-able libpq URL for `database` on the test server."""
    from sqlalchemy.engine.url import make_url

    base = make_url(_PG_URL).set(drivername="postgresql", database=database)
    return base.render_as_string(hide_password=False)


def _sa_url(database: str) -> str:
    """A SQLAlchemy URL (psycopg3 driver) for `database` — what the cfg carries.

    The helpers build a SQLAlchemy engine from ``cfg``'s ``sqlalchemy.url``; the
    bare ``postgresql://`` scheme would pick the absent psycopg2 driver, so use
    the explicit ``postgresql+psycopg`` form the production path normalises to.
    """
    from sqlalchemy.engine.url import make_url

    base = make_url(_PG_URL).set(drivername="postgresql+psycopg", database=database)
    return base.render_as_string(hide_password=False)


@pytest.mark.skipif(not _PG_URL, reason="no TEST_DATABASE_URL / DATABASE_URL — needs real Postgres")
def test_autostamp_reconciles_only_when_materialized() -> None:
    import psycopg
    from sqlalchemy import create_engine, text

    from dazzle.cli.db import (
        _alembic_version_is_empty,
        _autostamp_if_materialized,
        _get_alembic_cfg,
        _schema_is_materialized,
    )

    dbname = f"_dz_mig_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(_libpq_url("postgres"), autocommit=True) as adm:
        # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
        adm.execute(f'CREATE DATABASE "{dbname}"')

    try:
        cfg = _get_alembic_cfg()
        cfg.set_main_option("sqlalchemy.url", _sa_url(dbname))

        # ── Case 1: fresh DB — NOT materialized → no stamp (baseline must run).
        assert _schema_is_materialized(cfg) is False
        assert _alembic_version_is_empty(cfg) is True
        assert _autostamp_if_materialized(cfg) is False
        assert _alembic_version_is_empty(cfg) is True  # still unstamped

        # ── Case 2: materialize the schema (the `_dazzle_params` framework table)
        #     with alembic_version still empty → the reconcile case.
        with psycopg.connect(_libpq_url(dbname), autocommit=True) as conn:
            conn.execute(
                'CREATE TABLE "_dazzle_params" (key text, scope text, scope_id text, value text)'
            )
        assert _schema_is_materialized(cfg) is True
        assert _alembic_version_is_empty(cfg) is True
        assert _autostamp_if_materialized(cfg) is True  # it stamped
        # alembic_version now carries the head(s) — no longer empty.
        assert _alembic_version_is_empty(cfg) is False
        engine = create_engine(_sa_url(dbname))
        try:
            with engine.connect() as conn:
                n = conn.execute(text("SELECT count(*) FROM alembic_version")).scalar()
                assert (n or 0) >= 1
        finally:
            engine.dispose()

        # ── Case 3: idempotent — already stamped → no re-stamp.
        assert _autostamp_if_materialized(cfg) is False
    finally:
        with psycopg.connect(_libpq_url("postgres"), autocommit=True) as adm:
            # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
            adm.execute(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
