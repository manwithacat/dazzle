"""Real-PG proof of the connection substrate (auth Plan 4a)."""

from __future__ import annotations

import base64
import os
import uuid
from collections.abc import Iterator
from datetime import timedelta

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


_KEY_A = base64.b64encode(b"a" * 32).decode()
_KEY_B = base64.b64encode(b"b" * 32).decode()


def test_rewrap_all_connection_secrets_rotates_encryption_key(store_url: str, monkeypatch) -> None:
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY_A)
    store = _store(store_url)
    c1 = store.create_connection(
        tenant_id="org-1", type="oidc", config={}, secrets={"client_secret": "s1"}, domains=[]
    )
    c2 = store.create_connection(
        tenant_id="org-2", type="scim", config={}, secrets={"scim_bearer": "b2"}, domains=[]
    )
    # A connection with NO secret is ignored by the rewrap.
    store.create_connection(tenant_id="org-3", type="saml", config={}, secrets={}, domains=[])

    # Rotate: new key primary, old key as the rotation fallback.
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY_B)
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET_OLD", _KEY_A)
    res = store.rewrap_all_connection_secrets()
    assert res.rewrapped == 2 and res.already_current == 0 and res.failed == []

    # Now everything decrypts under ONLY the new key (the old key can be retired).
    monkeypatch.delenv("DAZZLE_CONNECTION_SECRET_OLD", raising=False)
    assert store.get_connection(c1.id).secrets["client_secret"] == "s1"
    assert store.get_connection(c2.id).secrets["scim_bearer"] == "b2"

    # Idempotent — a re-run rewraps nothing (all already on the primary key).
    res2 = store.rewrap_all_connection_secrets()
    assert res2.rewrapped == 0 and res2.already_current == 2 and res2.failed == []


def test_rewrap_reports_undecryptable_as_failed(store_url: str, monkeypatch) -> None:
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY_A)
    store = _store(store_url)
    c = store.create_connection(
        tenant_id="org-1", type="oidc", config={}, secrets={"client_secret": "s"}, domains=[]
    )
    # Rotate to a new key with NO old key set → the A-encrypted secret can't be decrypted.
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY_B)
    monkeypatch.delenv("DAZZLE_CONNECTION_SECRET_OLD", raising=False)
    res = store.rewrap_all_connection_secrets()
    assert res.failed == [c.id] and res.rewrapped == 0  # surfaced, never dropped


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


# ---- #1342 SCIM bearer grace window + rotation audit ----


def _make_scim_connection(store, bearer: str):
    return store.create_connection(
        tenant_id="org-1", type="scim", config={}, secrets={"scim_bearer": bearer}, domains=[]
    )


def test_scim_bearer_grace_window(store_url: str) -> None:
    store = _store(store_url)
    conn = _make_scim_connection(store, "old-bearer-xyz")
    assert store.rotate_connection_secret(
        conn.id, {"scim_bearer": "new-bearer-abc"}, grace=timedelta(hours=24), actor="cli"
    )
    # Both old and new authenticate during the window.
    assert store.get_scim_connection_by_bearer("new-bearer-abc").id == conn.id
    assert store.get_scim_connection_by_bearer("old-bearer-xyz").id == conn.id
    events = store.get_connection_secret_events(conn.id)
    assert events[0].event == "rotated" and events[0].detail["grace"] is True


def test_grace_expiry_rejects_old_bearer(store_url: str) -> None:
    store = _store(store_url)
    conn = _make_scim_connection(store, "old-b")
    store.rotate_connection_secret(
        conn.id, {"scim_bearer": "new-b"}, grace=timedelta(hours=1), actor="cli"
    )
    with psycopg.connect(store_url) as c:
        c.execute(
            "UPDATE connections SET previous_secret_expires_at=%s WHERE id=%s",
            ("2000-01-01T00:00:00+00:00", conn.id),
        )
        c.commit()
    assert store.get_scim_connection_by_bearer("new-b").id == conn.id
    assert store.get_scim_connection_by_bearer("old-b") is None  # expired


def test_revoke_previous_kills_old_bearer(store_url: str) -> None:
    store = _store(store_url)
    conn = _make_scim_connection(store, "old-b")
    store.rotate_connection_secret(
        conn.id, {"scim_bearer": "new-b"}, grace=timedelta(days=1), actor="cli"
    )
    assert store.revoke_previous_connection_secret(conn.id, actor="cli") is True
    assert store.get_scim_connection_by_bearer("old-b") is None
    assert store.get_scim_connection_by_bearer("new-b").id == conn.id
    # Idempotent: nothing left to revoke.
    assert store.revoke_previous_connection_secret(conn.id, actor="cli") is False
    assert {e.event for e in store.get_connection_secret_events(conn.id)} >= {
        "rotated",
        "revoked_previous",
    }


def test_hard_swap_clears_previous_and_audits(store_url: str) -> None:
    store = _store(store_url)
    conn = _make_scim_connection(store, "b1")
    store.rotate_connection_secret(
        conn.id, {"scim_bearer": "b2"}, grace=timedelta(days=1), actor="cli"
    )
    # A subsequent hard swap (no grace) must clear the grace secret.
    store.rotate_connection_secret(conn.id, {"scim_bearer": "b3"}, grace=None, actor="cli")
    assert store.get_scim_connection_by_bearer("b1") is None
    assert store.get_scim_connection_by_bearer("b2") is None
    assert store.get_scim_connection_by_bearer("b3").id == conn.id


def test_rewrap_covers_grace_blob(store_url: str, monkeypatch) -> None:
    store = _store(store_url)
    conn = _make_scim_connection(store, "b1")
    store.rotate_connection_secret(
        conn.id, {"scim_bearer": "b2"}, grace=timedelta(days=1), actor="cli"
    )
    # Rotate the master key: the old key becomes the rotation key, the new is primary.
    old_key = base64.b64encode(b"k" * 32).decode()
    new_key = base64.b64encode(b"j" * 32).decode()
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", new_key)
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET_OLD", old_key)
    result = store.rewrap_all_connection_secrets()
    assert result.failed == []
    # Both bearers still authenticate — the grace blob was re-encrypted too.
    assert store.get_scim_connection_by_bearer("b2").id == conn.id
    assert store.get_scim_connection_by_bearer("b1").id == conn.id
    assert "encryption_key_rewrapped" in {
        e.event for e in store.get_connection_secret_events(conn.id)
    }


def test_rewrap_rewraps_live_even_if_grace_blob_unreadable(store_url: str, monkeypatch) -> None:
    # Review #1342: a grace blob the rewrap can't decrypt must NOT strand the live
    # secret — the live blob still moves onto the new key (the bad grace blob is
    # reported in `failed`, not allowed to abandon the row).
    store = _store(store_url)
    conn = _make_scim_connection(store, "b1")
    store.rotate_connection_secret(
        conn.id, {"scim_bearer": "b2"}, grace=timedelta(days=1), actor="cli"
    )
    # Corrupt the grace blob so no key can decrypt it.
    with psycopg.connect(store_url) as c:
        c.execute(
            "UPDATE connections SET previous_encrypted_secret=%s WHERE id=%s",
            ("not-a-valid-blob", conn.id),
        )
        c.commit()
    old_key = base64.b64encode(b"k" * 32).decode()
    new_key = base64.b64encode(b"j" * 32).decode()
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", new_key)
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET_OLD", old_key)
    result = store.rewrap_all_connection_secrets()
    assert conn.id in result.failed  # the bad grace blob is reported
    # The live secret was still rewrapped — it authenticates with ONLY the new key.
    monkeypatch.delenv("DAZZLE_CONNECTION_SECRET_OLD")
    assert store.get_scim_connection_by_bearer("b2").id == conn.id


def test_rotate_grace_on_non_scim_rejected_at_store(store_url: str) -> None:
    # Review #1342: the SCIM-only grace contract is enforced in the store, not just
    # the CLI, so a future non-CLI caller can't store a useless grace blob.
    import pytest as _pytest

    store = _store(store_url)
    conn = store.create_connection(
        tenant_id="org-1", type="oidc", config={}, secrets={"client_secret": "s"}, domains=[]
    )
    with _pytest.raises(ValueError):
        store.rotate_connection_secret(
            conn.id, {"client_secret": "s2"}, grace=timedelta(hours=1), actor="cli"
        )


def test_get_connection_grace_status(store_url: str) -> None:
    store = _store(store_url)
    conn = _make_scim_connection(store, "b1")
    assert store.get_connection_grace_status(conn.id) == (False, None)
    store.rotate_connection_secret(
        conn.id, {"scim_bearer": "b2"}, grace=timedelta(days=1), actor="cli"
    )
    active, exp = store.get_connection_grace_status(conn.id)
    assert active is True and exp is not None
    store.revoke_previous_connection_secret(conn.id, actor="cli")
    assert store.get_connection_grace_status(conn.id) == (False, None)


def test_secret_reads_are_tenant_fenced(store_url: str) -> None:
    # Review #1342: get_connection_secret_events / get_connection_grace_status accept a
    # tenant_id fence (mirrors get_connection) — a cross-org id returns []/(False,None).
    store = _store(store_url)
    conn = _make_scim_connection(store, "b1")  # tenant org-1
    store.rotate_connection_secret(
        conn.id, {"scim_bearer": "b2"}, grace=timedelta(days=1), actor="cli"
    )
    # Same-org reads see the data.
    assert store.get_connection_secret_events(conn.id, tenant_id="org-1")
    assert store.get_connection_grace_status(conn.id, tenant_id="org-1")[0] is True
    # Cross-org reads are fenced.
    assert store.get_connection_secret_events(conn.id, tenant_id="org-2") == []
    assert store.get_connection_grace_status(conn.id, tenant_id="org-2") == (False, None)


def _make_saml_connection(store):
    return store.create_connection(
        tenant_id="org-1",
        type="saml",
        config={"idp_entity_id": "i", "idp_sso_url": "u", "idp_x509_cert": "c"},
        secrets={},
        domains=[],
    )


def test_enable_request_signing_persists_encrypted(store_url: str) -> None:
    store = _store(store_url)
    conn = _make_saml_connection(store)
    assert store.enable_connection_request_signing(
        conn.id, sp_cert="CERTPEM", sp_private_key="KEYPEM"
    )
    got = store.get_connection(conn.id)
    assert got.config["sp_cert"] == "CERTPEM"
    assert got.config["sign_requests"] == "true"
    assert got.secrets["sp_private_key"] == "KEYPEM"
    assert "KEYPEM" not in repr(got)  # masked
    with psycopg.connect(store_url) as c:
        row = c.execute(
            "SELECT config, encrypted_secret FROM connections WHERE id=%s", (conn.id,)
        ).fetchone()
    assert "KEYPEM" not in (row[0] or "") and "KEYPEM" not in (row[1] or "")  # never plaintext
    # Key-lifecycle is audited (review #1342).
    assert "sp_signing_enabled" in {e.event for e in store.get_connection_secret_events(conn.id)}


def test_disable_request_signing_clears(store_url: str) -> None:
    store = _store(store_url)
    conn = _make_saml_connection(store)
    store.enable_connection_request_signing(conn.id, sp_cert="CERT", sp_private_key="KEY")
    assert store.disable_connection_request_signing(conn.id) is True
    got = store.get_connection(conn.id)
    assert "sp_cert" not in got.config and "sign_requests" not in got.config
    assert "sp_private_key" not in (got.secrets or {})
    assert "sp_signing_disabled" in {e.event for e in store.get_connection_secret_events(conn.id)}
    assert store.disable_connection_request_signing(conn.id) is False  # idempotent


def test_enable_request_signing_rejects_non_saml(store_url: str) -> None:
    import pytest as _pytest

    store = _store(store_url)
    oidc = store.create_connection(
        tenant_id="org-1", type="oidc", config={}, secrets={"client_secret": "s"}, domains=[]
    )
    with _pytest.raises(ValueError):
        store.enable_connection_request_signing(oidc.id, sp_cert="C", sp_private_key="K")


def test_enable_request_signing_tenant_fenced(store_url: str) -> None:
    store = _store(store_url)
    conn = _make_saml_connection(store)
    assert (
        store.enable_connection_request_signing(
            conn.id, sp_cert="C", sp_private_key="K", tenant_id="org-2"
        )
        is False
    )


def test_migration_0012_adds_grace_and_audit(store_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    from dazzle.cli.db import _get_framework_alembic_dir

    _store(store_url)
    with psycopg.connect(store_url, autocommit=True) as c:
        c.execute("DROP TABLE IF EXISTS connection_secret_events")
        c.execute("ALTER TABLE connections DROP COLUMN IF EXISTS previous_encrypted_secret")
        c.execute("ALTER TABLE connections DROP COLUMN IF EXISTS previous_secret_expires_at")
    fw = _get_framework_alembic_dir()
    cfg = Config(str(fw / "alembic.ini"))
    cfg.set_main_option("script_location", str(fw))
    cfg.set_main_option("version_locations", str(fw / "versions"))
    cfg.set_main_option(
        "sqlalchemy.url", store_url.replace("postgresql://", "postgresql+psycopg://")
    )
    command.stamp(cfg, "0011_connections")
    command.upgrade(cfg, "0012_connection_grace_secret")
    with psycopg.connect(store_url) as c:
        tbl = c.execute(
            "SELECT to_regclass('public.connection_secret_events') IS NOT NULL"
        ).fetchone()[0]
        cols = {
            r[0]
            for r in c.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='connections'"
            ).fetchall()
        }
        ver = c.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert tbl is True
    assert {"previous_encrypted_secret", "previous_secret_expires_at"} <= cols
    assert ver == "0012_connection_grace_secret"


def test_encryption_and_signing_share_one_keypair(store_url: str) -> None:
    # The SP keypair is shared by request-signing and assertion-encryption; it must survive
    # disabling one feature and be removed only when BOTH are off (the lifecycle decouple).
    store = _store(store_url)
    conn = store.create_connection(
        tenant_id="org-enc",
        type="saml",
        config={"idp_entity_id": "x", "idp_sso_url": "y", "idp_x509_cert": "z"},
        secrets={},
        domains=[],
    )
    # Enable signing → keypair written.
    assert store.enable_connection_request_signing(conn.id, sp_cert="CERT", sp_private_key="KEY")
    # Enable encryption → reuses the SAME keypair (never clobbers), sets the flag.
    assert store.enable_connection_assertion_encryption(
        conn.id, sp_cert="CERT2", sp_private_key="KEY2"
    )
    got = store.get_connection(conn.id)
    assert got.config["encrypt_assertions"] == "true"
    assert got.config["sign_requests"] == "true"
    assert got.config["sp_cert"] == "CERT"  # NOT clobbered by the 2nd enable
    assert got.secrets["sp_private_key"] == "KEY"

    # Disable signing → keypair SURVIVES (encryption still on).
    assert store.disable_connection_request_signing(conn.id)
    got = store.get_connection(conn.id)
    assert "sign_requests" not in got.config
    assert got.config.get("sp_cert") == "CERT"  # kept for encryption
    assert got.secrets.get("sp_private_key") == "KEY"

    # Disable encryption → now both off → keypair removed.
    assert store.disable_connection_assertion_encryption(conn.id)
    got = store.get_connection(conn.id)
    assert "encrypt_assertions" not in got.config
    assert "sp_cert" not in got.config
    assert "sp_private_key" not in got.secrets

    # Audit trail recorded all four feature toggles.
    events = {e.event for e in store.get_connection_secret_events(conn.id)}
    assert {
        "sp_signing_enabled",
        "sp_signing_disabled",
        "sp_encryption_enabled",
        "sp_encryption_disabled",
    } <= events


def test_assertion_encryption_is_saml_only(store_url: str) -> None:
    store = _store(store_url)
    conn = store.create_connection(
        tenant_id="org-1", type="oidc", config={"issuer": "x"}, secrets={}, domains=[]
    )
    with pytest.raises(ValueError, match="SAML-only"):
        store.enable_connection_assertion_encryption(conn.id, sp_cert="C", sp_private_key="K")


def test_connection_type_counts(store_url: str) -> None:
    store = _store(store_url)
    store.create_connection(tenant_id="o", type="oidc", config={}, secrets={}, domains=[])
    store.create_connection(tenant_id="o", type="oidc", config={}, secrets={}, domains=[])
    store.create_connection(tenant_id="o", type="saml", config={}, secrets={}, domains=[])
    assert store.connection_type_counts() == {"oidc": 2, "saml": 1}


def test_connection_type_counts_missing_table_returns_empty(store_url: str) -> None:
    # A store whose schema was never initialised must not break boot — return {}.
    from dazzle.back.runtime.auth.store import AuthStore

    bare = AuthStore(database_url=store_url)  # no _init_db()
    assert bare.connection_type_counts() == {}
