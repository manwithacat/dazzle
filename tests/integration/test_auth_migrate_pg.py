"""Real-PG proof of `dazzle auth migrate` backfill (auth Plan 1d follow-up).

Mirrors domain tenant-root rows -> organizations (shared id) and creates a
membership per auth user (tenant resolved via the domain user entity by email).
Uses fixtures/tenant_rls (Workspace root + Member email->tenant entity)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
import sqlalchemy as sa

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_PROJECT_ROOT = Path("fixtures/tenant_rls")


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def scratch_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin_url = _admin_url()
    base, _, _old = admin_url.rpartition("/")
    scratch = f"dazzle_authmig_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep
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


def _setup(scratch_url: str):
    """tenant_rls schema + auth tables; seed 2 tenants, domain Members, auth users."""
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.auth.store import AuthStore
    from dazzle.http.runtime.sa_schema import build_metadata, scoped_entity_names

    appspec = load_project_appspec(_PROJECT_ROOT)
    pk = appspec.tenancy.isolation.partition_key
    scoped = sorted(scoped_entity_names(appspec.domain.entities, pk))
    md = build_metadata(
        convert_entities(appspec.domain.entities), partition_key=pk, tenant_scoped=scoped
    )
    engine = sa.create_engine(
        scratch_url.replace("postgresql://", "postgresql+psycopg://"), future=True
    )
    md.create_all(engine)
    store = AuthStore(database_url=scratch_url)
    store._init_db()

    ta, tb = str(uuid.uuid4()), str(uuid.uuid4())
    with psycopg.connect(scratch_url, autocommit=True) as c:
        c.execute(
            'INSERT INTO "Workspace" (id, name) VALUES (%s,%s),(%s,%s)',
            (ta, "Tenant A", tb, "Tenant B"),
        )
        c.execute(
            'INSERT INTO "Member" (tenant_id, id, email) VALUES (%s,%s,%s)',
            (ta, str(uuid.uuid4()), "alice@x.test"),
        )
        c.execute(
            'INSERT INTO "Member" (tenant_id, id, email) VALUES (%s,%s,%s)',
            (tb, str(uuid.uuid4()), "bob@x.test"),
        )
    # auth users: alice (in A), bob (in B), carol (no Member row → skipped).
    alice = store.create_user(email="alice@x.test", password="pw123456", roles=["worker"])
    bob = store.create_user(email="bob@x.test", password="pw123456", roles=["worker"])
    store.create_user(email="carol@x.test", password="pw123456", roles=["worker"])
    return appspec, store, ta, tb, alice, bob


def test_migrate_mirrors_orgs_and_creates_memberships(scratch_url: str) -> None:
    from dazzle.db.auth_migrate import migrate_to_memberships

    appspec, store, ta, tb, alice, bob = _setup(scratch_url)
    with psycopg.connect(scratch_url) as conn:
        res = migrate_to_memberships(appspec, conn=conn, user_entity="Member")

    assert res.orgs_mirrored == 2
    assert res.memberships_created == 2
    assert res.users_skipped == ["carol@x.test"]
    # Orgs mirror the Workspace ids (shared id).
    assert store.get_organization(ta) is not None
    assert store.get_organization(tb) is not None
    # alice fenced to A, bob to B.
    am = store.get_memberships_for_identity(str(alice.id))
    bm = store.get_memberships_for_identity(str(bob.id))
    assert [m.tenant_id for m in am] == [ta]
    assert [m.tenant_id for m in bm] == [tb]


def test_migrate_is_idempotent(scratch_url: str) -> None:
    from dazzle.db.auth_migrate import migrate_to_memberships

    appspec, store, _ta, _tb, _a, _b = _setup(scratch_url)
    with psycopg.connect(scratch_url) as conn:
        migrate_to_memberships(appspec, conn=conn, user_entity="Member")
    with psycopg.connect(scratch_url) as conn:
        res2 = migrate_to_memberships(appspec, conn=conn, user_entity="Member")
    assert res2.orgs_mirrored == 0
    assert res2.memberships_created == 0


def test_migrate_dry_run_writes_nothing(scratch_url: str) -> None:
    from dazzle.db.auth_migrate import migrate_to_memberships

    appspec, store, _ta, _tb, _a, _b = _setup(scratch_url)
    with psycopg.connect(scratch_url) as conn:
        res = migrate_to_memberships(appspec, conn=conn, user_entity="Member", dry_run=True)
    assert res.orgs_mirrored == 2 and res.memberships_created == 2  # would-counts
    with psycopg.connect(scratch_url) as c:
        assert c.execute("SELECT count(*) FROM organizations").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM memberships").fetchone()[0] == 0
