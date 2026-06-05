"""Real-PostgreSQL proof of tenant excision isolation (RLS Phase E.1, #1338).

Marked e2e + postgres: skipped without TEST_DATABASE_URL/DATABASE_URL. Loads the
`fixtures/tenant_rls` AppSpec (Workspace root + Member/Project/Task scoped),
seeds two tenants + auth-store orgs/memberships/identities, excises one, and
asserts the other is untouched (the critical isolation property) plus precise
orphaned-identity reaping. Connects as the scratch superuser (bypasses RLS — the
excision-as-dazzle_bypass posture); the isolation here is the WHERE-clause
discipline + the deletion order, not RLS.
"""

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
    scratch = f"dazzle_excise_{uuid.uuid4().hex[:8]}"
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


def _load_appspec_and_metadata():
    from dazzle.back.converters.entity_converter import convert_entities
    from dazzle.back.runtime.sa_schema import build_metadata, scoped_entity_names
    from dazzle.core.appspec_loader import load_project_appspec

    appspec = load_project_appspec(_PROJECT_ROOT)
    pk = appspec.tenancy.isolation.partition_key
    scoped = sorted(scoped_entity_names(appspec.domain.entities, pk))
    md = build_metadata(
        convert_entities(appspec.domain.entities), partition_key=pk, tenant_scoped=scoped
    )
    return appspec, md


def _seed_domain(engine: sa.Engine, md: sa.MetaData) -> tuple[str, str]:
    """Seed tenants A and B with Member/Project/Task descendants. Returns (A, B)
    as string UUIDs (the fixture's id columns are uuid; org ids = these
    discriminators, the canonical invariant)."""
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    ws, member, project, task = (
        md.tables["Workspace"],
        md.tables["Member"],
        md.tables["Project"],
        md.tables["Task"],
    )
    with engine.begin() as conn:
        conn.execute(ws.insert(), [{"id": a, "name": "A"}, {"id": b, "name": "B"}])
        for t in (a, b):
            mid, pid, tid = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
            conn.execute(member.insert(), [{"tenant_id": t, "id": mid, "email": f"m-{t}@x.test"}])
            conn.execute(
                project.insert(),
                [{"tenant_id": t, "id": pid, "name": f"proj-{t}", "owner": mid}],
            )
            conn.execute(
                task.insert(),
                [{"tenant_id": t, "id": tid, "title": f"task-{t}", "project": pid}],
            )
    return a, b


def _seed_auth(scratch_url: str, a: str, b: str) -> tuple[str, str]:
    """Seed orgs (id=A,B), one A-only identity + one identity shared across A,B.
    Returns (only_a_id, shared_id)."""
    from dazzle.back.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    store.create_organization(slug="org-a", name="A")
    store.create_organization(slug="org-b", name="B")
    with psycopg.connect(scratch_url) as conn:
        conn.execute("UPDATE organizations SET id=%s WHERE slug='org-a'", (a,))
        conn.execute("UPDATE organizations SET id=%s WHERE slug='org-b'", (b,))
        conn.commit()
    only_a = store.create_user(email="only-a@b.test", password="pw123456")
    shared = store.create_user(email="shared@b.test", password="pw123456")
    store.create_membership(tenant_id=a, identity_id=str(only_a.id), roles=["worker"])
    store.create_membership(tenant_id=a, identity_id=str(shared.id), roles=["worker"])
    store.create_membership(tenant_id=b, identity_id=str(shared.id), roles=["worker"])
    return str(only_a.id), str(shared.id)


def _count(url: str, sql: str, *params) -> int:
    with psycopg.connect(url) as c:
        return int(c.execute(sql, params).fetchone()[0])


def test_excise_removes_tenant_a_and_leaves_b(scratch_url: str) -> None:
    from dazzle.db.excision import excise_tenant

    appspec, md = _load_appspec_and_metadata()
    engine = sa.create_engine(
        scratch_url.replace("postgresql://", "postgresql+psycopg://"), future=True
    )
    md.create_all(engine)
    a, b = _seed_domain(engine, md)
    only_a, shared = _seed_auth(scratch_url, a, b)

    with psycopg.connect(scratch_url) as conn:
        result = excise_tenant(appspec, a, conn=conn)

    # A gone at every level + auth cascade.
    assert _count(scratch_url, 'SELECT count(*) FROM "Workspace" WHERE id=%s', a) == 0
    assert _count(scratch_url, 'SELECT count(*) FROM "Project" WHERE tenant_id=%s', a) == 0
    assert _count(scratch_url, 'SELECT count(*) FROM "Task" WHERE tenant_id=%s', a) == 0
    assert _count(scratch_url, 'SELECT count(*) FROM "Member" WHERE tenant_id=%s', a) == 0
    assert _count(scratch_url, "SELECT count(*) FROM memberships WHERE tenant_id=%s", a) == 0
    assert _count(scratch_url, "SELECT count(*) FROM organizations WHERE id=%s", a) == 0
    # B fully intact — the isolation assertion.
    assert _count(scratch_url, 'SELECT count(*) FROM "Workspace" WHERE id=%s', b) == 1
    assert _count(scratch_url, 'SELECT count(*) FROM "Project" WHERE tenant_id=%s', b) == 1
    assert _count(scratch_url, 'SELECT count(*) FROM "Task" WHERE tenant_id=%s', b) == 1
    assert _count(scratch_url, 'SELECT count(*) FROM "Member" WHERE tenant_id=%s', b) == 1
    assert _count(scratch_url, "SELECT count(*) FROM memberships WHERE tenant_id=%s", b) == 1
    assert _count(scratch_url, "SELECT count(*) FROM organizations WHERE id=%s", b) == 1
    # Precise reaping: only-a orphaned → gone; shared still in B → kept.
    assert _count(scratch_url, "SELECT count(*) FROM users WHERE id=%s", only_a) == 0
    assert _count(scratch_url, "SELECT count(*) FROM users WHERE id=%s", shared) == 1
    assert result.deleted["Task"] == 1
    assert result.deleted["memberships"] == 2
    assert result.deleted["users"] == 1
    assert result.deleted["organizations"] == 1


def test_excise_dry_run_deletes_nothing(scratch_url: str) -> None:
    from dazzle.db.excision import excise_tenant

    appspec, md = _load_appspec_and_metadata()
    engine = sa.create_engine(
        scratch_url.replace("postgresql://", "postgresql+psycopg://"), future=True
    )
    md.create_all(engine)
    a, b = _seed_domain(engine, md)
    _seed_auth(scratch_url, a, b)

    with psycopg.connect(scratch_url) as conn:
        result = excise_tenant(appspec, a, conn=conn, dry_run=True)

    # Nothing deleted.
    assert _count(scratch_url, 'SELECT count(*) FROM "Workspace"') == 2
    assert _count(scratch_url, "SELECT count(*) FROM memberships WHERE tenant_id=%s", a) == 2
    assert _count(scratch_url, "SELECT count(*) FROM organizations") == 2
    # Counts still reported (would-delete).
    assert result.dry_run is True
    assert result.deleted["Workspace"] == 1
    assert result.deleted["memberships"] == 2
