"""Real-PG proof of the connection substrate (auth Plan 4a)."""

from __future__ import annotations

import base64
import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture(autouse=True)
def _conn_key(monkeypatch):
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(b"k" * 32).decode())


@pytest.fixture
def store_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _PG_URL.replace("postgresql+psycopg://", "postgresql://")
    base, _, _old = admin.rpartition("/")
    scratch = f"dazzle_conn_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep
    try:
        yield url
    finally:
        with psycopg.connect(admin, autocommit=True) as a:
            a.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=%s AND pid<>pg_backend_pid()",
                (scratch,),
            )
            a.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


def _store(store_url: str):
    from dazzle.back.runtime.auth.store import AuthStore

    s = AuthStore(database_url=store_url)
    s._init_db()
    return s


def test_create_stores_secret_encrypted_and_reads_decrypted(store_url: str) -> None:
    store = _store(store_url)
    conn = store.create_connection(
        tenant_id="org-1",
        type="oidc",
        config={"issuer": "https://idp.example", "client_id": "abc"},
        secrets={"client_secret": "TOP-SECRET"},
        domains=["acme.test"],
    )
    # The secret is NOT in the row as plaintext (only the encrypted blob).
    with psycopg.connect(store_url) as c:
        row = c.execute(
            "SELECT config, encrypted_secret FROM connections WHERE id=%s", (conn.id,)
        ).fetchone()
    assert "TOP-SECRET" not in (row[0] or "") and "TOP-SECRET" not in (row[1] or "")
    assert row[1] is not None  # an encrypted blob is stored
    # Read decrypts the secret + keeps non-secret config plaintext.
    got = store.get_connection(conn.id)
    assert got.secrets["client_secret"] == "TOP-SECRET"
    assert got.config["issuer"] == "https://idp.example"
    # The repr must not leak the secret value.
    assert "TOP-SECRET" not in repr(got)


def test_connections_fenced_by_tenant(store_url: str) -> None:
    store = _store(store_url)
    store.create_connection(tenant_id="org-A", type="oidc", config={}, secrets={}, domains=[])
    store.create_connection(tenant_id="org-B", type="scim", config={}, secrets={}, domains=[])
    a = store.get_connections_for_tenant("org-A")
    assert len(a) == 1 and a[0].type == "oidc"


def test_verified_domain_routing_only_matches_verified(store_url: str) -> None:
    store = _store(store_url)
    conn = store.create_connection(
        tenant_id="org-1",
        type="oidc",
        config={},
        secrets={},
        domains=["acme.test"],  # claimed but NOT verified
    )
    # An unverified claimed domain must NOT route (anti-hijack).
    assert store.get_connection_by_verified_domain("acme.test") is None
    # After verification it routes (case-insensitive).
    store.set_connection_verified_domains(conn.id, ["acme.test"])
    routed = store.get_connection_by_verified_domain("ACME.test")
    assert routed is not None and routed.tenant_id == "org-1"


def test_get_connection_tenant_scoped_fences_cross_org(store_url: str) -> None:
    store = _store(store_url)
    conn = store.create_connection(
        tenant_id="org-1", type="oidc", config={}, secrets={"client_secret": "s"}, domains=[]
    )
    # Same-org read returns it (with decrypted secrets); cross-org read is None.
    assert store.get_connection(conn.id, tenant_id="org-1") is not None
    assert store.get_connection(conn.id, tenant_id="org-2") is None  # fenced
    # Unscoped read still works (internal use), returns the record.
    assert store.get_connection(conn.id) is not None


def test_delete_connection(store_url: str) -> None:
    store = _store(store_url)
    conn = store.create_connection(
        tenant_id="org-1", type="oidc", config={}, secrets={}, domains=[]
    )
    assert store.delete_connection(conn.id) is True
    assert store.get_connection(conn.id) is None


def test_migration_0011_creates_connections(store_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    from dazzle.cli.db import _get_framework_alembic_dir

    _store(store_url)
    with psycopg.connect(store_url, autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS connections")
    fw = _get_framework_alembic_dir()
    cfg = Config(str(fw / "alembic.ini"))
    cfg.set_main_option("script_location", str(fw))
    cfg.set_main_option("version_locations", str(fw / "versions"))
    cfg.set_main_option(
        "sqlalchemy.url", store_url.replace("postgresql://", "postgresql+psycopg://")
    )
    command.stamp(cfg, "0010_invitations")
    command.upgrade(cfg, "0011_connections")
    with psycopg.connect(store_url) as c:
        ok = c.execute("SELECT to_regclass('public.connections') IS NOT NULL").fetchone()[0]
        ver = c.execute("SELECT version_num FROM alembic_version").fetchone()
    assert ok is True
    assert ver is not None and ver[0] == "0011_connections"
