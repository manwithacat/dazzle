"""Coexistence drift gate (#1342): the alembic auth-mirror migrations must run cleanly against
a DB that ``AuthStore._init_db`` already built — the REAL prod order (``_init_db`` creates the
base tables on every AuthStore boot; ``dazzle db upgrade`` then alters as guarded no-ops). The
alembic chain is NOT standalone — 0005/0007 ALTER ``sessions``, which only ``_init_db`` creates
— so "alembic on an empty DB" is not a valid path; this asserts the path that actually runs.

The companion static gate (tests/unit/test_authstore_alembic_mirror_completeness) enforces that
every _init_db table is mirrored. Together: completeness (static) + coexistence (here)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
import sqlalchemy as sa

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture
def scratch_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _PG_URL.replace("postgresql+psycopg://", "postgresql://")
    base, _, _ = admin.rpartition("/")
    name = f"dazzle_parity_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{name}"')  # nosemgrep
    try:
        yield f"{base}/{name}"
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()",
                (name,),
            )
            a.execute(f'DROP DATABASE IF EXISTS "{name}"')  # nosemgrep


def _alembic_head(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    from dazzle.cli.db import _get_framework_alembic_dir

    fw = _get_framework_alembic_dir()
    cfg = Config(str(fw / "alembic.ini"))
    cfg.set_main_option("script_location", str(fw))
    cfg.set_main_option("path_separator", "os")
    cfg.set_main_option("version_locations", str(fw / "versions"))  # framework only
    cfg.set_main_option("sqlalchemy.url", url.replace("postgresql://", "postgresql+psycopg://", 1))
    command.upgrade(cfg, "head")


def test_alembic_head_coexists_with_init_db(scratch_url: str) -> None:
    # The real prod order: _init_db builds the base schema, then alembic upgrade head runs as
    # guarded ALTERs/creates. This must succeed (no "column already exists" / no missing table)
    # — proving the mirror migrations (incl. 0013/0014/0015) are correctly guarded.
    from dazzle.back.runtime.auth.store import AuthStore

    AuthStore(database_url=scratch_url)  # _init_db
    _alembic_head(scratch_url)  # must NOT raise

    eng = sa.create_engine(scratch_url.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        insp = sa.inspect(eng)
        # alembic head recorded, and the new tables/columns are present (from _init_db, and
        # 0013/0014/0015 no-op over them) — schema intact after both ran.
        version = eng.connect().execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "0016_saml_consumed_assertions"
        assert insp.has_table("saml_consumed_assertions")
        assert "external_id" in {c["name"] for c in insp.get_columns("memberships")}
        assert "external_id" in {c["name"] for c in insp.get_columns("scim_groups")}
        assert insp.has_table("scim_group_members")
        # the partial unique index 0014 mirrors must exist (from _init_db; 0014 no-ops over it)
        index_names = {ix["name"] for ix in insp.get_indexes("memberships")}
        assert "uq_memberships_tenant_external" in index_names
        # the case-insensitive email index 0015 mirrors must exist (from _init_db; 0015 no-ops)
        user_index_names = {ix["name"] for ix in insp.get_indexes("users")}
        assert "users_email_lower_key" in user_index_names
    finally:
        eng.dispose()


def test_alembic_head_on_empty_after_init_db_is_idempotent(scratch_url: str) -> None:
    # Running upgrade head twice (re-deploy) must stay clean.
    from dazzle.back.runtime.auth.store import AuthStore

    AuthStore(database_url=scratch_url)
    _alembic_head(scratch_url)
    _alembic_head(scratch_url)  # second run — no error
