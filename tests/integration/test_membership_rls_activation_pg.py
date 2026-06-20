"""Canonical proof: a provisioned membership fences real RLS domain data as a
non-superuser (auth Plan 1d). Loads fixtures/tenant_rls, applies RLS, provisions
a single org (Workspace + organizations, shared id), and verifies the fence."""

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
_APP_PW = "app-pw"  # noqa: S105 — fixture-local non-secret


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def scratch_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin_url = _admin_url()
    base, _, _old = admin_url.rpartition("/")
    scratch = f"dazzle_memact_{uuid.uuid4().hex[:8]}"
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


def _appspec_and_md():
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.sa_schema import build_metadata, scoped_entity_names

    appspec = load_project_appspec(_PROJECT_ROOT)
    pk = appspec.tenancy.isolation.partition_key
    scoped = sorted(scoped_entity_names(appspec.domain.entities, pk))
    md = build_metadata(
        convert_entities(appspec.domain.entities), partition_key=pk, tenant_scoped=scoped
    )
    return appspec, md, pk, scoped


def _make(scratch_url: str):
    from dazzle.http.runtime.auth.store import AuthStore

    appspec, md, pk, scoped = _appspec_and_md()
    engine = sa.create_engine(
        scratch_url.replace("postgresql://", "postgresql+psycopg://"), future=True
    )
    md.create_all(engine)
    store = AuthStore(database_url=scratch_url)
    store._init_db()
    return appspec, md, pk, scoped, store


# ── Task 3: provision_single_org 1:1 mirror ──────────────────────────────────


def test_provision_single_org_mirrors_tenant_root_id(scratch_url: str) -> None:
    from dazzle.db.provision import provision_single_org

    appspec, _md, _pk, _scoped, _store = _make(scratch_url)
    with psycopg.connect(scratch_url) as conn:
        org_id = provision_single_org(appspec, "Acme", conn=conn)

    with psycopg.connect(scratch_url) as c:
        ws = c.execute('SELECT id FROM "Workspace" WHERE id=%s', (org_id,)).fetchone()
        org = c.execute("SELECT id FROM organizations WHERE id=%s", (org_id,)).fetchone()
    assert ws is not None and str(ws[0]) == org_id  # tenant-root row at the shared id
    assert org is not None and str(org[0]) == org_id  # org mirrors it


def test_provision_single_org_idempotent(scratch_url: str) -> None:
    from dazzle.db.provision import provision_single_org

    appspec, _md, _pk, _scoped, _store = _make(scratch_url)
    with psycopg.connect(scratch_url) as conn:
        a = provision_single_org(appspec, "Acme", conn=conn)
    with psycopg.connect(scratch_url) as conn:
        b = provision_single_org(appspec, "Acme", conn=conn)
    assert a == b  # same default org, no second Workspace
    with psycopg.connect(scratch_url) as c:
        assert c.execute('SELECT count(*) FROM "Workspace"').fetchone()[0] == 1


# ── Task 4: ensure_single_org_membership routes through the mirror ───────────


def test_ensure_membership_uses_mirrored_org_for_archetype_app(scratch_url: str) -> None:
    appspec, _md, _pk, _scoped, store = _make(scratch_url)
    user = store.create_user(email="w@b.test", password="pw123456", roles=["worker"])
    m = store.ensure_single_org_membership(user, name="Acme", appspec=appspec)
    with psycopg.connect(scratch_url) as c:
        ws = c.execute('SELECT id FROM "Workspace" WHERE id=%s', (m.tenant_id,)).fetchone()
    assert ws is not None, "membership.tenant_id must equal a real Workspace row id"


# ── Task 5: canonical proof — membership fences RLS data as a non-superuser ──


def _conn_url(scratch_url: str, role: str, password: str) -> str:
    head, _, hostpart = scratch_url.partition("://")
    host_only = hostpart.split("@")[-1].rpartition("/")[0]
    db = scratch_url.rpartition("/")[2]
    return f"{head}://{role}:{password}@{host_only}/{db}"


def test_membership_fences_rls_data_as_non_superuser(scratch_url: str) -> None:
    from dazzle.http.runtime.rls_schema import build_rls_policy_ddl

    appspec, _md, pk, scoped, store = _make(scratch_url)

    # Tenant A: provisioned via the 1:1 mirror (Workspace + org, shared id) + a
    # member with a membership in it.
    user = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.ensure_single_org_membership(user, name="Tenant A", appspec=appspec)
    org_a = m.tenant_id

    # Tenant B: a second Workspace + a Project, seeded directly (superuser).
    org_b = str(uuid.uuid4())
    with psycopg.connect(scratch_url, autocommit=True) as c:
        c.execute('INSERT INTO "Workspace" (id, name) VALUES (%s, %s)', (org_b, "Tenant B"))
        for tid, label in ((org_a, "A-proj"), (org_b, "B-proj")):
            mid = str(uuid.uuid4())
            c.execute(
                'INSERT INTO "Member" (tenant_id, id, email) VALUES (%s,%s,%s)',
                (tid, mid, f"{label}@x.test"),
            )
            c.execute(
                'INSERT INTO "Project" (tenant_id, id, name, owner) VALUES (%s,%s,%s,%s)',
                (tid, str(uuid.uuid4()), label, mid),
            )

    # Apply the framework RLS policies + a NON-superuser login role (superusers
    # bypass RLS — the fence is only observable as a non-superuser).
    role = f"memact_app_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(scratch_url, autocommit=True) as c:
        for stmt in build_rls_policy_ddl(scoped, partition_key=pk):
            c.execute(stmt)  # nosemgrep — framework-generated DDL
        c.execute(f"CREATE ROLE \"{role}\" LOGIN PASSWORD 'app-pw'")  # nosemgrep — uuid-derived
        c.execute(f'GRANT USAGE ON SCHEMA public TO "{role}"')  # nosemgrep
        c.execute(f'GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO "{role}"')  # nosemgrep

    try:
        # Bound to the membership's tenant_id → sees only tenant A's rows.
        with psycopg.connect(_conn_url(scratch_url, role, "app-pw")) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('dazzle.tenant_id', %s, false)", (org_a,))
                rows = cur.execute('SELECT name FROM "Project"').fetchall()
            conn.rollback()
        # A FRESH session with the GUC never bound → current_setting(...,true) is
        # NULL → the restrictive fence denies all (fail-closed).
        with psycopg.connect(_conn_url(scratch_url, role, "app-pw")) as conn2:
            denied = conn2.execute('SELECT count(*) FROM "Project"').fetchall()
            conn2.rollback()
    finally:
        with psycopg.connect(scratch_url, autocommit=True) as c:
            c.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{role}"')  # nosemgrep
            c.execute(f'REVOKE USAGE ON SCHEMA public FROM "{role}"')  # nosemgrep
            c.execute(f'DROP ROLE IF EXISTS "{role}"')  # nosemgrep

    assert {r[0] for r in rows} == {"A-proj"}, "membership must fence to tenant A only"
    assert denied[0][0] == 0, "unbound dazzle.tenant_id must deny all (fail-closed)"
