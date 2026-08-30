"""Real-PG proof of signing-on-A DEFINER lookup (ADR-0055 D5).

As ``dazzle_app`` (LOGIN, no BYPASSRLS) with the fence GUC unset:

* ``dazzle_signing_lookup_tenant`` for a signable ``record_id`` returns
  the partition id (function owner is ``dazzle_bypass`` / BYPASSRLS).
* leftover / non-signable ``p_entity`` returns NULL (no existence oracle).
* a subsequent SELECT as ``dazzle_app`` after binding the GUC sees the row.
* a SELECT with GUC still unset still sees 0 rows (FORCE fence holds).

Skipped without ``TEST_DATABASE_URL`` / ``DATABASE_URL``. Marked ``e2e`` +
``postgres`` so Tier 1 / ci-core skip it; CI postgres-tests run it.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from types import SimpleNamespace

import psycopg
import pytest

from dazzle.http.runtime.rls_schema import build_rls_policy_ddl, build_signing_lookup_ddl

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_APP_PW = "rls_test_app_pw"
_BYPASS_PW = "rls_test_bypass_pw"


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def signing_db() -> Iterator[dict[str, str]]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")

    suffix = uuid.uuid4().hex[:8]
    scratch = f"dazzle_sign_lookup_{suffix}"
    owner_role = f"dazzle_owner_{suffix}"
    app_role = f"dazzle_app_{suffix}"
    bypass_role = f"dazzle_bypass_{suffix}"
    admin_url = _admin_url()
    base, _, _old = admin_url.rpartition("/")
    scratch_url = f"{base}/{scratch}"
    tenant_id = str(uuid.uuid4())
    record_id = str(uuid.uuid4())

    created_db = False
    try:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep — uuid-derived
            created_db = True

        with psycopg.connect(scratch_url, autocommit=True) as admin:
            admin.execute('CREATE TABLE "Contract" (id uuid PRIMARY KEY, tenant_id uuid NOT NULL)')
            admin.execute(  # nosemgrep — uuid-derived role
                f'CREATE ROLE "{owner_role}" NOLOGIN'
            )
            admin.execute(  # nosemgrep — uuid-derived role; fixture password
                f"CREATE ROLE \"{app_role}\" LOGIN PASSWORD '{_APP_PW}'"
            )
            admin.execute(  # nosemgrep — uuid-derived role; BYPASSRLS by design
                f"CREATE ROLE \"{bypass_role}\" LOGIN PASSWORD '{_BYPASS_PW}' BYPASSRLS"
            )
            admin.execute(  # nosemgrep — uuid-derived roles
                f'GRANT USAGE ON SCHEMA public TO "{app_role}", "{bypass_role}", "{owner_role}"'
            )
            admin.execute(  # nosemgrep — uuid-derived roles
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public "
                f'TO "{app_role}", "{bypass_role}", "{owner_role}"'
            )
            for stmt in build_rls_policy_ddl(["Contract"], partition_key="tenant_id"):
                admin.execute(stmt)
            admin.execute(
                'INSERT INTO "Contract" (id, tenant_id) VALUES (%s, %s)',
                (record_id, tenant_id),
            )
            entity = SimpleNamespace(
                name="Contract",
                signable=True,
                fields=[SimpleNamespace(name="id"), SimpleNamespace(name="tenant_id")],
            )
            appspec = SimpleNamespace(
                domain=SimpleNamespace(entities=[entity]),
                tenancy=SimpleNamespace(isolation=SimpleNamespace(partition_key="tenant_id")),
            )
            for stmt in build_signing_lookup_ddl(appspec):
                rewritten = stmt.replace("dazzle_bypass", bypass_role).replace(
                    "dazzle_app", app_role
                )
                admin.execute(rewritten)

        yield {
            "scratch_url": scratch_url,
            "app_role": app_role,
            "bypass_role": bypass_role,
            "tenant_id": tenant_id,
            "record_id": record_id,
        }
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            if created_db:
                admin.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (scratch,),
                )
                admin.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep
            for role in (app_role, bypass_role, owner_role):
                admin.execute(f'DROP ROLE IF EXISTS "{role}"')  # nosemgrep


def _app_conn(info: dict[str, str]) -> psycopg.Connection:
    head, _, hostpart = info["scratch_url"].partition("://")
    host_only = hostpart.split("@")[-1]
    url = f"{head}://{info['app_role']}:{_APP_PW}@{host_only}"
    return psycopg.connect(url)


def test_definer_lookup_returns_partition_id_with_guc_unset(signing_db: dict[str, str]) -> None:
    with _app_conn(signing_db) as conn:
        row = conn.execute(
            "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
        ).fetchone()
        assert row is not None
        assert row[1] is False
        assert row[2] is False
        hidden = conn.execute(
            'SELECT count(*) FROM "Contract" WHERE id = %s',
            (signing_db["record_id"],),
        ).fetchone()
        assert hidden is not None and hidden[0] == 0
        found = conn.execute(
            "SELECT dazzle_signing_lookup_tenant(%s, %s::uuid)",
            ("Contract", signing_db["record_id"]),
        ).fetchone()
        assert found is not None
        assert str(found[0]) == signing_db["tenant_id"]


def test_leftover_entity_name_returns_null(signing_db: dict[str, str]) -> None:
    with _app_conn(signing_db) as conn:
        found = conn.execute(
            "SELECT dazzle_signing_lookup_tenant(%s, %s::uuid)",
            ("zzz", signing_db["record_id"]),
        ).fetchone()
        assert found is not None
        assert found[0] is None


def test_bind_then_read_as_app_succeeds(signing_db: dict[str, str]) -> None:
    with _app_conn(signing_db) as conn:
        with conn.transaction():
            conn.execute(
                "SELECT set_config('dazzle.tenant_id', %s, true)",
                (signing_db["tenant_id"],),
            )
            row = conn.execute(
                'SELECT tenant_id FROM "Contract" WHERE id = %s',
                (signing_db["record_id"],),
            ).fetchone()
        assert row is not None
        assert str(row[0]) == signing_db["tenant_id"]
