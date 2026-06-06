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


def test_claim_verified_domain_enforces_one_owner(store_url: str) -> None:
    store = _store(store_url)
    c1 = store.create_connection(
        tenant_id="org-1", type="oidc", config={}, secrets={}, domains=["acme.test"]
    )
    c2 = store.create_connection(
        tenant_id="org-2", type="oidc", config={}, secrets={}, domains=["acme.test"]
    )
    # First connection claims the domain; the second cannot (one owner per domain).
    assert store.claim_verified_domain(c1.id, "acme.test") is True
    assert store.claim_verified_domain(c2.id, "acme.test") is False
    # Idempotent re-claim by the owner.
    assert store.claim_verified_domain(c1.id, "ACME.test.") is True  # normalized
    routed = store.get_connection_by_verified_domain("acme.test")
    assert routed is not None and routed.id == c1.id
    # The losing connection never got the domain in its verified list.
    assert "acme.test" not in (store.get_connection(c2.id).verified_domains or [])


def test_claim_verified_domain_unknown_connection(store_url: str) -> None:
    store = _store(store_url)
    assert store.claim_verified_domain("nonexistent", "acme.test") is False


def test_update_connection_secrets_rotates_and_re_encrypts(store_url: str) -> None:
    store = _store(store_url)
    conn = store.create_connection(
        tenant_id="org-1", type="oidc", config={}, secrets={"client_secret": "OLD"}, domains=[]
    )
    old_updated = store.get_connection(conn.id).updated_at
    # Rotate the secret.
    assert store.update_connection_secrets(conn.id, {"client_secret": "NEW"}) is True
    refreshed = store.get_connection(conn.id)
    assert refreshed.secrets["client_secret"] == "NEW"  # decrypts the rotated value
    assert refreshed.updated_at >= old_updated  # bumped → OIDC client cache rebuilds
    # Neither the old nor the new plaintext is stored in the row.
    with psycopg.connect(store_url) as c:
        enc = c.execute(
            "SELECT encrypted_secret FROM connections WHERE id=%s", (conn.id,)
        ).fetchone()[0]
    assert "NEW" not in (enc or "") and "OLD" not in (enc or "")
    # Tenant fence: a wrong-org write changes nothing.
    assert (
        store.update_connection_secrets(conn.id, {"client_secret": "X"}, tenant_id="org-2") is False
    )
    assert store.get_connection(conn.id).secrets["client_secret"] == "NEW"
    # Unknown connection → False.
    assert store.update_connection_secrets("nonexistent", {"client_secret": "X"}) is False


def test_get_scim_connection_by_bearer(store_url: str) -> None:
    store = _store(store_url)
    c = store.create_connection(
        tenant_id="org-1", type="scim", config={}, secrets={"scim_bearer": "tok-123"}, domains=[]
    )
    # An OIDC connection with no bearer must never match.
    store.create_connection(tenant_id="org-2", type="oidc", config={}, secrets={}, domains=[])
    assert store.get_scim_connection_by_bearer("tok-123").id == c.id
    assert store.get_scim_connection_by_bearer("wrong-token") is None
    assert store.get_scim_connection_by_bearer("") is None


def test_delete_sessions_for_membership_is_org_scoped(store_url: str) -> None:
    store = _store(store_url)
    user = store.create_user(email="jane@acme.test", password="pw-placeholder-1")
    m1 = store.create_membership(tenant_id="org-1", identity_id=str(user.id))
    m2 = store.create_membership(tenant_id="org-2", identity_id=str(user.id))
    store.create_session(user, active_membership_id=m1.id)
    store.create_session(user, active_membership_id=m2.id)
    assert store.count_active_sessions(user.id) == 2
    # Revoke only the org-1 membership's sessions; the org-2 session survives.
    assert store.delete_sessions_for_membership(m1.id) == 1
    assert store.count_active_sessions(user.id) == 1
    assert store.delete_sessions_for_membership(m1.id) == 0  # idempotent


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
