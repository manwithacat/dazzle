"""Canonical proof: create-time tenant_id injection fences writes as a
non-superuser (auth Plan 1d). A scoped INSERT that omits tenant_id is filled
from the bound session GUC by the column's `current_setting('dazzle.tenant_id')`
server_default; an unbound session fails closed; an explicit foreign tenant_id
is denied by the RLS WITH CHECK. Loads fixtures/tenant_rls and applies the
framework RLS policies, exercised as a NON-superuser role (superusers bypass
RLS, so the fence is only observable as a non-superuser)."""

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
    scratch = f"dazzle_createinj_{uuid.uuid4().hex[:8]}"
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


def _conn_url(scratch_url: str, role: str, password: str) -> str:
    head, _, hostpart = scratch_url.partition("://")
    host_only = hostpart.split("@")[-1].rpartition("/")[0]
    db = scratch_url.rpartition("/")[2]
    return f"{head}://{role}:{password}@{host_only}/{db}"


def _build_app_role(scratch_url: str, scoped: list[str], pk: str) -> str:
    """Apply RLS + a non-superuser LOGIN role with SELECT/INSERT. Returns the role."""
    from dazzle.http.runtime.rls_schema import build_rls_policy_ddl

    role = f"createinj_app_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(scratch_url, autocommit=True) as c:
        for stmt in build_rls_policy_ddl(scoped, partition_key=pk):
            c.execute(stmt)  # nosemgrep — framework-generated DDL
        c.execute(f"CREATE ROLE \"{role}\" LOGIN PASSWORD 'app-pw'")  # nosemgrep — uuid-derived
        c.execute(f'GRANT USAGE ON SCHEMA public TO "{role}"')  # nosemgrep
        c.execute(f'GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO "{role}"')  # nosemgrep
    return role


def _drop_app_role(scratch_url: str, role: str) -> None:
    with psycopg.connect(scratch_url, autocommit=True) as c:
        c.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{role}"')  # nosemgrep
        c.execute(f'REVOKE USAGE ON SCHEMA public FROM "{role}"')  # nosemgrep
        c.execute(f'DROP ROLE IF EXISTS "{role}"')  # nosemgrep


def test_scoped_insert_omitting_tenant_id_autofills_from_bound_guc(scratch_url: str) -> None:
    """A non-superuser INSERT that omits tenant_id is server-filled from the bound
    session GUC (the column server_default), and lands in-tenant."""
    _appspec, md, pk, scoped = _appspec_and_md()
    engine = sa.create_engine(
        scratch_url.replace("postgresql://", "postgresql+psycopg://"), future=True
    )
    md.create_all(engine)

    org_a = str(uuid.uuid4())
    with psycopg.connect(scratch_url, autocommit=True) as c:
        c.execute('INSERT INTO "Workspace" (id, name) VALUES (%s, %s)', (org_a, "Tenant A"))
        owner_id = str(uuid.uuid4())
        c.execute(
            'INSERT INTO "Member" (tenant_id, id, email) VALUES (%s,%s,%s)',
            (org_a, owner_id, "owner@a.test"),
        )

    role = _build_app_role(scratch_url, scoped, pk)
    try:
        with psycopg.connect(_conn_url(scratch_url, role, "app-pw")) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('dazzle.tenant_id', %s, false)", (org_a,))
                # NOTE: tenant_id intentionally omitted — the column default fills it.
                returned = cur.execute(
                    'INSERT INTO "Project" (id, name, owner) VALUES (%s,%s,%s) RETURNING tenant_id',
                    (str(uuid.uuid4()), "A-proj", owner_id),
                ).fetchone()
            conn.rollback()
    finally:
        _drop_app_role(scratch_url, role)

    assert returned is not None
    assert str(returned[0]) == org_a, "omitted tenant_id must be filled from the bound GUC"


def test_unbound_session_scoped_insert_fails_closed(scratch_url: str) -> None:
    """With no dazzle.tenant_id bound, current_setting(...,true) is NULL so the
    server_default yields a NULL partition key. The write is denied — fail-closed.
    Two independent guards reject it: the RLS WITH CHECK (NULL tenant_id ≠ NULL
    GUC; NULL = NULL is not true) and the NOT NULL column constraint. PG evaluates
    the RLS check first, so the observed error is InsufficientPrivilege; accept
    either, since both prove no NULL/wrong-tenant row is written."""
    _appspec, md, pk, scoped = _appspec_and_md()
    engine = sa.create_engine(
        scratch_url.replace("postgresql://", "postgresql+psycopg://"), future=True
    )
    md.create_all(engine)

    role = _build_app_role(scratch_url, scoped, pk)
    try:
        with psycopg.connect(_conn_url(scratch_url, role, "app-pw")) as conn:
            with pytest.raises(
                (psycopg.errors.InsufficientPrivilege, psycopg.errors.NotNullViolation)
            ):
                conn.execute(
                    'INSERT INTO "Project" (id, name, owner) VALUES (%s,%s,%s)',
                    (str(uuid.uuid4()), "orphan", str(uuid.uuid4())),
                )
            conn.rollback()
    finally:
        _drop_app_role(scratch_url, role)


def test_explicit_foreign_tenant_id_is_denied_by_with_check(scratch_url: str) -> None:
    """Defense-in-depth: even if the input-exclusion were bypassed, a session
    bound to tenant A that writes an explicit foreign tenant_id is denied by the
    RLS fence's WITH CHECK."""
    _appspec, md, pk, scoped = _appspec_and_md()
    engine = sa.create_engine(
        scratch_url.replace("postgresql://", "postgresql+psycopg://"), future=True
    )
    md.create_all(engine)

    org_a, org_b = str(uuid.uuid4()), str(uuid.uuid4())
    with psycopg.connect(scratch_url, autocommit=True) as c:
        for tid, label in ((org_a, "Tenant A"), (org_b, "Tenant B")):
            c.execute('INSERT INTO "Workspace" (id, name) VALUES (%s, %s)', (tid, label))

    role = _build_app_role(scratch_url, scoped, pk)
    try:
        with psycopg.connect(_conn_url(scratch_url, role, "app-pw")) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('dazzle.tenant_id', %s, false)", (org_a,))
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    cur.execute(
                        'INSERT INTO "Project" (tenant_id, id, name, owner) VALUES (%s,%s,%s,%s)',
                        (org_b, str(uuid.uuid4()), "smuggled", str(uuid.uuid4())),
                    )
            conn.rollback()
    finally:
        _drop_app_role(scratch_url, role)
