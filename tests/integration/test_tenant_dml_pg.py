"""Real-PostgreSQL proof of the #1778 seam-DML tripwire + ``for_each_tenant``.

The cyfuture failure: ``dazzle db upgrade`` ran a hand-authored backfill at the
data-migration seam against a database where RLS was ALREADY applied. As a
non-superuser, non-``BYPASSRLS`` table owner under ``FORCE ROW LEVEL SECURITY``
with no ``dazzle.tenant_id`` bound, the ``INSERT … SELECT`` read zero rows and
inserted nothing — no error.

Each test stands up a scratch DB, creates a uniquely-suffixed LOGIN
NOSUPERUSER NOBYPASSRLS owner role, and — **as that owner** — creates the
``fixtures/tenant_rls`` schema + the auth tables and applies RLS with the
production ``apply_rls_policies`` (RLS first, the release-phase order). Rows for
two tenants are seeded through the superuser admin connection. The assertions
then run as the owner:

1. control: the unbound backfill silently inserts 0 rows (the bug);
2. under the tripwire (``arm_rls_tripwire`` → ``SET LOCAL row_security = off``)
   the same statement raises the Postgres RLS error;
3. under the same tripwire, ``for_each_tenant`` inserts each tenant's rows and
   restores ``row_security`` + the tenant GUC.

Marked ``e2e`` + ``postgres``: skipped without ``TEST_DATABASE_URL`` /
``DATABASE_URL``.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import psycopg
import pytest
import sqlalchemy as sa
from psycopg import errors as pg_errors

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_PROJECT_ROOT = Path("fixtures/tenant_rls")
_OWNER_PW = "tenant_dml_owner_pw"  # fixture-only test password, never a real secret
_MEMBERS = {"a": 2, "b": 3}  # members seeded per tenant

# The seam backfill under test: copy every member of the bound tenant. Reads and
# writes a fenced table, exactly the shape that silently matched nothing.
_BACKFILL = (
    'INSERT INTO "Member" (tenant_id, id, email) '
    "SELECT m.tenant_id, gen_random_uuid(), 'copy-' || m.email "
    "FROM \"Member\" m WHERE m.email NOT LIKE 'copy-%'"
)


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


def _with_db(url: str, db: str, *, user: str | None = None, pw: str | None = None) -> str:
    head, _, rest = url.partition("://")
    creds, _, hostpart = rest.rpartition("@")
    host_only = hostpart.rpartition("/")[0]
    if user is None:
        prefix = f"{creds}@" if creds else ""
    else:
        prefix = f"{user}:{pw}@"
    return f"{head}://{prefix}{host_only}/{db}"


@dataclass
class _Harness:
    admin_url: str
    owner_url: str
    tenants: dict[str, str]  # key → tenant id


@pytest.fixture
def harness() -> Iterator[_Harness]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")

    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.db.connection import get_connection
    from dazzle.db.rls_apply import apply_rls_policies
    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.auth.store import ensure_auth_core_tables
    from dazzle.http.runtime.sa_schema import build_metadata, scoped_entity_names

    suffix = uuid.uuid4().hex[:8]
    scratch = f"dazzle_tenant_dml_{suffix}"
    owner = f"dazzle_owner_{suffix}"
    admin_url = _admin_url()
    scratch_admin = _with_db(admin_url, scratch)
    owner_url = _with_db(admin_url, scratch, user=owner, pw=_OWNER_PW)
    owner_engine: sa.Engine | None = None
    try:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep — uuid-derived db name
            admin.execute(  # nosemgrep — uuid-derived role; fixture password
                f"CREATE ROLE \"{owner}\" LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{_OWNER_PW}'"
            )
        with psycopg.connect(scratch_admin, autocommit=True) as admin:
            admin.execute(f'GRANT CREATE, USAGE ON SCHEMA public TO "{owner}"')  # nosemgrep

        appspec = load_project_appspec(_PROJECT_ROOT)
        pk = appspec.tenancy.isolation.partition_key
        entities = convert_entities(appspec.domain.entities)
        scoped = sorted(scoped_entity_names(appspec.domain.entities, pk))

        # Everything below runs AS THE OWNER: it owns the tables, so FORCE RLS
        # (not a superuser bypass) is what governs its DML.
        owner_engine = sa.create_engine(owner_url.replace("postgresql://", "postgresql+psycopg://"))
        build_metadata(entities, partition_key=pk, tenant_scoped=scoped).create_all(owner_engine)
        with psycopg.connect(owner_url) as conn, conn.cursor() as cur:
            ensure_auth_core_tables(cur)

        async def _apply() -> int:
            conn = await get_connection(explicit_url=owner_url)
            try:
                return await apply_rls_policies(conn, appspec, entities)
            finally:
                await conn.close()

        assert asyncio.run(_apply()) > 0, "RLS must be applied before the migration"

        # Seed via the superuser admin (bypasses the fence — setup, not a claim).
        tenants = {k: str(uuid.uuid4()) for k in _MEMBERS}
        with psycopg.connect(scratch_admin) as admin:
            for key, tid in tenants.items():
                admin.execute(
                    "INSERT INTO organizations (id, slug, name, created_at, updated_at) "
                    "VALUES (%s, %s, %s, now()::text, now()::text)",
                    (tid, f"org-{key}", f"Org {key}"),
                )
                admin.execute('INSERT INTO "Workspace" (id, name) VALUES (%s, %s)', (tid, key))
                for i in range(_MEMBERS[key]):
                    admin.execute(
                        'INSERT INTO "Member" (tenant_id, id, email) VALUES (%s, %s, %s)',
                        (tid, str(uuid.uuid4()), f"{key}{i}@example.test"),
                    )
        yield _Harness(admin_url=scratch_admin, owner_url=owner_url, tenants=tenants)
    finally:
        if owner_engine is not None:
            owner_engine.dispose()
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (scratch,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep — uuid-derived
            admin.execute(f'DROP ROLE IF EXISTS "{owner}"')  # nosemgrep — uuid-derived role


def _member_counts(h: _Harness) -> dict[str, int]:
    with psycopg.connect(h.admin_url) as admin:
        rows = admin.execute('SELECT tenant_id::text, count(*) FROM "Member" GROUP BY 1').fetchall()
    by_id = dict(rows)
    return {key: by_id.get(tid, 0) for key, tid in h.tenants.items()}


def _assert_plain_owner(conn: Any) -> None:
    row = conn.execute(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    assert tuple(row) == (False, False), (
        f"owner must not bypass RLS (proof would be vacuous): {row}"
    )


def test_unbound_backfill_is_silent_without_tripwire_and_raises_with_it(harness: _Harness) -> None:
    h = harness
    from dazzle.http.alembic.tenant_dml import arm_rls_tripwire

    with psycopg.connect(h.owner_url) as conn:
        _assert_plain_owner(conn)
        # Control — the #1778 bug: no error, nothing inserted.
        with conn.transaction():
            assert conn.execute(_BACKFILL).rowcount == 0

        # Tripwire armed: the same statement is an error, not a no-op.
        with pytest.raises(
            pg_errors.InsufficientPrivilege, match="would be affected by row-level security"
        ):
            with conn.transaction():
                arm_rls_tripwire(conn)
                conn.execute(_BACKFILL)

    assert _member_counts(h) == _MEMBERS


def test_for_each_tenant_backfills_every_tenant_under_the_tripwire(harness: _Harness) -> None:
    h = harness
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from dazzle.http.alembic.tenant_dml import arm_rls_tripwire, for_each_tenant

    engine = sa.create_engine(h.owner_url.replace("postgresql://", "postgresql+psycopg://"))
    try:
        with engine.begin() as conn:
            _assert_plain_owner(conn.connection.dbapi_connection)
            arm_rls_tripwire(conn.connection)  # what env.py does for the upgrade tx
            with Operations.context(MigrationContext.configure(conn)):
                counts = for_each_tenant(_BACKFILL)
            # Tripwire and fail-closed tenant state are back after the helper.
            assert conn.exec_driver_sql("SHOW row_security").scalar() == "off"
            guc = conn.exec_driver_sql("SELECT current_setting('dazzle.tenant_id', true)")
            assert guc.scalar() == ""
    finally:
        engine.dispose()

    assert counts == {h.tenants[k]: n for k, n in _MEMBERS.items()}
    assert _member_counts(h) == {k: 2 * n for k, n in _MEMBERS.items()}
