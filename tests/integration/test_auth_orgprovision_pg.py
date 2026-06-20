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
    from dazzle.http.runtime.auth.store import AuthStore

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

    from dazzle.cli.db import _get_framework_alembic_dir
    from dazzle.http.runtime.auth.store import AuthStore

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
    # Target 0008 explicitly (NOT "head") so this stays pinned to 0008 in
    # isolation as later migrations extend the chain.
    command.upgrade(cfg, "0008_organizations")

    assert {"id", "slug", "name", "status", "is_test"} <= _columns(scratch_url, "organizations")


# -- Task 3: organization CRUD (race-safe get-or-create) ---------------------


def test_get_or_create_default_organization_is_idempotent(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()

    o1 = store.get_or_create_default_organization(name="Acme")
    o2 = store.get_or_create_default_organization(name="Acme")
    assert o1.id == o2.id  # same row — not a second org
    assert o1.slug == "default"
    assert store.get_organization_by_slug("default").id == o1.id


def test_create_organization_slug_unique(scratch_url: str) -> None:
    import pytest

    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    store.create_organization(slug="acme", name="Acme")
    with pytest.raises(Exception):  # noqa: B017 — unique violation
        store.create_organization(slug="acme", name="Acme 2")


# -- Task 4: ensure_single_org_membership ------------------------------------


def test_ensure_single_org_membership_first_and_second_user(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

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


# -- Task 5: lazy provisioning at activation (real PG) -----------------------


def test_activation_provisions_and_auto_activates(scratch_url: str) -> None:
    from types import SimpleNamespace

    from dazzle.http.runtime.auth.org_activation import (
        Activated,
        activate_session_for_login,
    )
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="solo@b.test", password="pw123456", roles=["member"])

    app = SimpleNamespace(state=SimpleNamespace(single_org_auto_provision=True))
    request = SimpleNamespace(app=app, state=SimpleNamespace(tenant=None))

    out = activate_session_for_login(store, user, request)
    assert isinstance(out, Activated)
    m = store.get_membership(out.membership_id)
    assert m.roles == ["member"]
    assert store.get_organization_by_slug("default").id == m.tenant_id


def test_host_pin_does_not_auto_provision(scratch_url: str) -> None:
    """A host-pinned request to an org the user isn't in stays 403 — provisioning
    must not paper over it."""
    from types import SimpleNamespace

    from dazzle.http.runtime.auth.org_activation import (
        HostForbidden,
        activate_session_for_login,
    )
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="solo@b.test", password="pw123456", roles=["member"])

    app = SimpleNamespace(state=SimpleNamespace(single_org_auto_provision=True))
    request = SimpleNamespace(
        app=app, state=SimpleNamespace(tenant=SimpleNamespace(id="t-pinned", slug="acme"))
    )
    out = activate_session_for_login(store, user, request)
    assert isinstance(out, HostForbidden)
    assert store.get_organization_by_slug("default") is None


# -- Task 6: ServerConfig flag default (non-breaking) ------------------------


def test_server_config_defaults_auto_provision_off() -> None:
    """Non-breaking default: existing apps don't auto-provision (no DB needed)."""
    from dazzle.http.runtime.server import ServerConfig

    assert ServerConfig().auto_provision_single_org is False


# -- Task 7: keystone — provisioned membership binds the fence ---------------


def test_provisioned_membership_binds_fence(scratch_url: str) -> None:
    """A provisioned membership's tenant_id binds dazzle.tenant_id; a restrictive
    fence returns only that org's rows (mirrors the 1a keystone)."""
    from types import SimpleNamespace

    from dazzle.http.runtime.auth.org_activation import activate_session_for_login
    from dazzle.http.runtime.auth.store import AuthStore

    ddl = [
        'CREATE TABLE "Note" (tenant_id TEXT NOT NULL, id TEXT PRIMARY KEY, body TEXT)',
        'ALTER TABLE "Note" ENABLE ROW LEVEL SECURITY',
        'ALTER TABLE "Note" FORCE ROW LEVEL SECURITY',
        # Permissive baseline + restrictive fence (the real Phase-B shape): a
        # restrictive policy alone default-denies (it only ANDs over a permissive
        # one), so the baseline is required for any row to be visible.
        'CREATE POLICY tenant_baseline ON "Note" AS PERMISSIVE FOR ALL '
        "USING (true) WITH CHECK (true)",
        'CREATE POLICY tenant_fence ON "Note" AS RESTRICTIVE FOR ALL '
        "USING (tenant_id = current_setting('dazzle.tenant_id', true)) "
        "WITH CHECK (tenant_id = current_setting('dazzle.tenant_id', true))",
    ]
    with psycopg.connect(scratch_url, autocommit=True) as conn:
        for stmt in ddl:
            conn.execute(stmt)  # nosemgrep — static test DDL

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="solo@b.test", password="pw123456", roles=["member"])
    app = SimpleNamespace(state=SimpleNamespace(single_org_auto_provision=True))
    request = SimpleNamespace(app=app, state=SimpleNamespace(tenant=None))
    out = activate_session_for_login(store, user, request)
    org_id = store.get_membership(out.membership_id).tenant_id

    # Seed both tenants' rows + a NOSUPERUSER role to read under — superusers
    # bypass RLS entirely, so the fence is only observable as a non-superuser
    # (the real `dazzle_app` model; mirrors test_rls_enforcement_pg.py).
    role = f"orgfence_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(scratch_url, autocommit=True) as conn:
        conn.execute('INSERT INTO "Note" VALUES (%s, %s, %s)', (org_id, "n1", "mine"))
        conn.execute('INSERT INTO "Note" VALUES (%s, %s, %s)', ("t-other", "n2", "theirs"))
        conn.execute(f'CREATE ROLE "{role}" NOSUPERUSER')  # nosemgrep — uuid-derived
        conn.execute(f'GRANT SELECT ON "Note" TO "{role}"')  # nosemgrep

    try:
        with psycopg.connect(scratch_url) as conn:
            with conn.cursor() as cur:
                cur.execute(f'SET ROLE "{role}"')  # nosemgrep — RLS now applies
                # session-scoped GUC so it's set regardless of SET ROLE's txn timing
                cur.execute("SELECT set_config('dazzle.tenant_id', %s, false)", (org_id,))
                rows = cur.execute('SELECT id FROM "Note"').fetchall()
                cur.execute("RESET ROLE")
            conn.rollback()
    finally:
        # Roles are cluster-global (not dropped by DROP DATABASE) — drop ours so
        # it can't leak/collide across runs, even if the assertion below fails.
        with psycopg.connect(scratch_url, autocommit=True) as conn:
            conn.execute(f'REVOKE ALL ON "Note" FROM "{role}"')  # nosemgrep
            conn.execute(f'DROP ROLE IF EXISTS "{role}"')  # nosemgrep
    assert {r[0] for r in rows} == {"n1"}, "fence must return only the provisioned org's row"
