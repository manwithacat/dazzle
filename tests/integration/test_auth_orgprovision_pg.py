"""Real-PostgreSQL proof of single-org auto-provision (auth Plan 1c).

Marked e2e + postgres: skipped without TEST_DATABASE_URL/DATABASE_URL.
Mirrors tests/integration/test_auth_membership_pg.py's scratch-DB + alembic harness.
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
def scratch_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin_url = _admin_url()
    base, _, _old = admin_url.rpartition("/")
    scratch = f"dazzle_auth_1c_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep — uuid-derived
    try:
        yield url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (scratch,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


def _columns(url: str, table: str) -> set[str]:
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        ).fetchall()
    return {r[0] for r in rows}


# -- Task 2: organizations table (migration + _init_db parity) ---------------


def test_init_db_creates_organizations(scratch_url: str) -> None:
    from dazzle.back.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    cols = _columns(scratch_url, "organizations")
    assert {"id", "slug", "name", "status", "is_test"} <= cols


def test_migration_0008_applies_on_a_pre_0008_db(scratch_url: str) -> None:
    """Migration 0008 creates `organizations` and lands at revision 0008.

    Same realistic scenario as 0007's test: a deployed DB with the auth tables
    present (via `_init_db`), stamped at the prior head, then apply only 0008.
    """
    from alembic import command
    from alembic.config import Config

    from dazzle.back.runtime.auth.store import AuthStore
    from dazzle.cli.db import _get_framework_alembic_dir

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    with psycopg.connect(scratch_url, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS organizations")

    fw = _get_framework_alembic_dir()
    cfg = Config(str(fw / "alembic.ini"))
    cfg.set_main_option("script_location", str(fw))
    cfg.set_main_option("version_locations", str(fw / "versions"))
    cfg.set_main_option(
        "sqlalchemy.url", scratch_url.replace("postgresql://", "postgresql+psycopg://")
    )
    command.stamp(cfg, "0007_memberships")  # mark the DB as at the prior head
    command.upgrade(cfg, "head")  # applies only 0008

    assert {"id", "slug", "name", "status", "is_test"} <= _columns(scratch_url, "organizations")


# -- Task 3: organization CRUD (race-safe get-or-create) ---------------------


def test_get_or_create_default_organization_is_idempotent(scratch_url: str) -> None:
    from dazzle.back.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()

    o1 = store.get_or_create_default_organization(name="Acme")
    o2 = store.get_or_create_default_organization(name="Acme")
    assert o1.id == o2.id  # same row — not a second org
    assert o1.slug == "default"
    assert store.get_organization_by_slug("default").id == o1.id


def test_create_organization_slug_unique(scratch_url: str) -> None:
    import pytest

    from dazzle.back.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    store.create_organization(slug="acme", name="Acme")
    with pytest.raises(Exception):  # noqa: B017 — unique violation
        store.create_organization(slug="acme", name="Acme 2")


# -- Task 4: ensure_single_org_membership ------------------------------------


def test_ensure_single_org_membership_first_and_second_user(scratch_url: str) -> None:
    from dazzle.back.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    u1 = store.create_user(email="a@b.test", password="pw123456", roles=["member"])
    u2 = store.create_user(email="b@b.test", password="pw123456", roles=["member"])

    m1 = store.ensure_single_org_membership(u1, name="Acme")
    m2 = store.ensure_single_org_membership(u2, name="Acme")
    # Both joined the SAME org.
    assert m1.tenant_id == m2.tenant_id
    # The membership carries the user's signup roles.
    assert m1.roles == ["member"]
    # Idempotent: calling again for u1 returns the existing membership, no dup.
    m1_again = store.ensure_single_org_membership(u1, name="Acme")
    assert m1_again.id == m1.id
    assert len(store.get_memberships_for_identity(str(u1.id))) == 1
