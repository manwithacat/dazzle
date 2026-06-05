"""`dazzle auth connection` CLI tests (auth Plan 4b.iv).

Monkeypatches the store (and, for the success path, the DNS resolver) so the CLI
wiring + error paths run without Postgres or real DNS.
"""

import base64
from datetime import datetime

import pytest
from typer.testing import CliRunner

from dazzle.cli import auth_connection
from dazzle.cli.auth import auth_app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(b"k" * 32).decode())


class _Conn:
    def __init__(self, cid="conn-1", *, domains=None, verified=None):
        self.id = cid
        self.tenant_id = "org-1"
        self.type = "oidc"
        self.status = "active"
        self.domains = domains or []
        self.verified_domains = verified or []


class _Store:
    def __init__(self, *, conn=None, owner_of=None):
        self._conn = conn
        self._owner_of = owner_of or {}
        self.created = None
        self.set_domains_calls: list = []
        self.claim_calls: list = []
        self.deleted: list = []

    def create_connection(self, **kw):
        self.created = kw
        return _Conn("conn-new")

    def get_connections_for_tenant(self, tenant):
        return [self._conn] if self._conn else []

    def get_connection(self, cid, *, tenant_id=None):
        return self._conn if (self._conn and self._conn.id == cid) else None

    def set_connection_domains(self, cid, domains):
        self.set_domains_calls.append((cid, domains))

    def get_connection_by_verified_domain(self, domain):
        return self._owner_of.get(domain.strip().lower())

    def claim_verified_domain(self, connection_id, domain):
        norm = domain.strip().lower()
        owner = self._owner_of.get(norm)
        if owner is not None and owner.id != connection_id:
            return False
        self.claim_calls.append((connection_id, norm))
        return True

    def delete_connection(self, cid):
        self.deleted.append(cid)
        return self._conn is not None and self._conn.id == cid


def _patch_store(monkeypatch, store):
    monkeypatch.setattr(auth_connection, "_store", lambda: store)


# ---- create / list / delete ----


def test_create(monkeypatch) -> None:
    store = _Store()
    _patch_store(monkeypatch, store)
    r = runner.invoke(
        auth_app,
        [
            "connection",
            "create",
            "--tenant",
            "org-1",
            "--issuer",
            "https://idp.example",
            "--client-id",
            "cid",
            "--client-secret",
            "shh",
            "--group-map",
            "eng=engineer",
        ],
    )
    assert r.exit_code == 0 and "conn-new" in r.output
    assert store.created["tenant_id"] == "org-1"
    assert store.created["secrets"] == {"client_secret": "shh"}
    assert store.created["group_mapping"] == {"eng": "engineer"}


def test_create_bad_group_map(monkeypatch) -> None:
    _patch_store(monkeypatch, _Store())
    r = runner.invoke(
        auth_app,
        [
            "connection",
            "create",
            "--tenant",
            "org-1",
            "--issuer",
            "https://i",
            "--client-id",
            "c",
            "--client-secret",
            "s",
            "--group-map",
            "noequals",
        ],
    )
    assert r.exit_code != 0


def test_delete_missing(monkeypatch) -> None:
    _patch_store(monkeypatch, _Store(conn=None))
    r = runner.invoke(auth_app, ["connection", "delete", "conn-x"])
    assert r.exit_code == 1 and "No connection" in r.output


# ---- add-domain ----


def test_add_domain_prints_txt_and_claims(monkeypatch) -> None:
    store = _Store(conn=_Conn("conn-1"))
    _patch_store(monkeypatch, store)
    r = runner.invoke(auth_app, ["connection", "add-domain", "conn-1", "ACME.test"])
    assert r.exit_code == 0
    assert "dazzle-verify=" in r.output  # the TXT record to publish
    assert store.set_domains_calls == [("conn-1", ["acme.test"])]  # normalized + claimed


def test_add_domain_missing_connection(monkeypatch) -> None:
    _patch_store(monkeypatch, _Store(conn=None))
    r = runner.invoke(auth_app, ["connection", "add-domain", "conn-x", "acme.test"])
    assert r.exit_code == 1 and "No connection" in r.output


# ---- verify-domain ----


def test_verify_domain_already_owned_elsewhere(monkeypatch) -> None:
    conn = _Conn("conn-1")
    other = _Conn("conn-2")
    store = _Store(conn=conn, owner_of={"acme.test": other})
    _patch_store(monkeypatch, store)
    # The uniqueness check raises before any DNS lookup — no network needed.
    r = runner.invoke(auth_app, ["connection", "verify-domain", "conn-1", "acme.test"])
    assert r.exit_code == 1 and "already verified" in r.output.lower()
    assert store.claim_calls == []


def test_verify_domain_success(monkeypatch) -> None:
    from dazzle.back.runtime.auth import domain_verification

    conn = _Conn("conn-1")
    store = _Store(conn=conn)
    _patch_store(monkeypatch, store)
    expected = domain_verification.txt_record("conn-1", "acme.test")

    class _FakeResolver:
        def resolve_txt(self, domain):
            return [expected]

    monkeypatch.setattr(domain_verification, "DnspythonResolver", _FakeResolver)
    r = runner.invoke(auth_app, ["connection", "verify-domain", "conn-1", "acme.test"])
    assert r.exit_code == 0 and "Verified" in r.output
    assert store.claim_calls == [("conn-1", "acme.test")]


def test_verify_domain_not_found_prints_record(monkeypatch) -> None:
    from dazzle.back.runtime.auth import domain_verification

    conn = _Conn("conn-1")
    _patch_store(monkeypatch, _Store(conn=conn))

    class _EmptyResolver:
        def resolve_txt(self, domain):
            return []

    monkeypatch.setattr(domain_verification, "DnspythonResolver", _EmptyResolver)
    r = runner.invoke(auth_app, ["connection", "verify-domain", "conn-1", "acme.test"])
    assert r.exit_code == 1 and "dazzle-verify=" in r.output  # shows the record to add


# ---- show-verification ----


def test_show_verification(monkeypatch) -> None:
    _patch_store(monkeypatch, _Store())
    r = runner.invoke(auth_app, ["connection", "show-verification", "conn-1", "acme.test"])
    assert r.exit_code == 0 and "dazzle-verify=" in r.output


# ---- doctor / scaffold (Plan 4b.v) ----


def _oidc_conn(**over):
    from dazzle.back.runtime.auth.connections import ConnectionRecord

    base = {
        "id": "conn-1",
        "tenant_id": "org-1",
        "type": "oidc",
        "provider": "native",
        "domains": ["acme.test"],
        "verified_domains": ["acme.test"],
        "config": {"issuer": "https://idp.example", "client_id": "cid"},
        "secrets": {"client_secret": "SUPER-SECRET"},
        "group_mapping": {"eng": "engineer"},
        "status": "active",
        "created_at": datetime(2026, 6, 6),
        "updated_at": datetime(2026, 6, 6),
    }
    base.update(over)
    return ConnectionRecord(**base)


def _patch_doctor(monkeypatch, conn, flags=(True, True, True)):
    store = _Store(conn=conn)
    monkeypatch.setattr(auth_connection, "_store", lambda: store)
    monkeypatch.setattr(auth_connection, "_env_flags", lambda: flags)
    return store


def test_doctor_ready_exit_0(monkeypatch) -> None:
    _patch_doctor(monkeypatch, _oidc_conn())
    r = runner.invoke(auth_app, ["connection", "doctor", "conn-1"])
    assert r.exit_code == 0 and "Activation-ready" in r.output


def test_doctor_not_ready_exit_1(monkeypatch) -> None:
    _patch_doctor(monkeypatch, _oidc_conn(verified_domains=[]))
    r = runner.invoke(auth_app, ["connection", "doctor", "conn-1"])
    assert r.exit_code == 1 and "Not activation-ready" in r.output


def test_doctor_never_leaks_secret(monkeypatch) -> None:
    _patch_doctor(monkeypatch, _oidc_conn(secrets={"client_secret": "SUPER-SECRET"}))
    r = runner.invoke(auth_app, ["connection", "doctor", "conn-1"])
    assert "SUPER-SECRET" not in r.output
    r2 = runner.invoke(auth_app, ["connection", "doctor", "conn-1", "--json"])
    assert "SUPER-SECRET" not in r2.output


def test_doctor_json_carries_ready(monkeypatch) -> None:
    _patch_doctor(monkeypatch, _oidc_conn())
    r = runner.invoke(auth_app, ["connection", "doctor", "conn-1", "--json"])
    assert r.exit_code == 0 and '"ready"' in r.output and "conn-1" in r.output


def test_doctor_no_key_blocks_before_load(monkeypatch) -> None:
    # secret_key_ok=False → never loads the connection, single remedy, exit 1.
    _patch_doctor(monkeypatch, _oidc_conn(), flags=(False, True, True))
    r = runner.invoke(auth_app, ["connection", "doctor", "conn-1"])
    assert r.exit_code == 1 and "DAZZLE_CONNECTION_SECRET" in r.output


def test_doctor_missing_connection(monkeypatch) -> None:
    _patch_doctor(monkeypatch, None)
    r = runner.invoke(auth_app, ["connection", "doctor", "conn-x"])
    assert r.exit_code == 1 and "No connection" in r.output


def test_scaffold_prints_sequence(monkeypatch) -> None:
    r = runner.invoke(auth_app, ["connection", "scaffold"])
    assert r.exit_code == 0
    assert "verify-domain" in r.output and "/auth/enterprise/callback" in r.output


def test_doctor_rotated_key_json_parity(monkeypatch) -> None:
    # Key present (flags say so) but get_connection raises ConnectionSecretError
    # (wrong/rotated key). With --json the agent must still get JSON, not markup.
    from dazzle.back.runtime.auth.connection_crypto import ConnectionSecretError

    class _RaisingStore:
        def get_connection(self, cid, *, tenant_id=None):
            raise ConnectionSecretError("auth failed")

    monkeypatch.setattr(auth_connection, "_store", lambda: _RaisingStore())
    monkeypatch.setattr(auth_connection, "_env_flags", lambda: (True, True, True))
    r = runner.invoke(auth_app, ["connection", "doctor", "conn-1", "--json"])
    assert r.exit_code == 1
    assert '"blocked"' in r.output and "secret_decrypt" in r.output
