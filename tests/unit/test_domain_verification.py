"""Domain-verification kernel tests (auth Plan 4b.iv).

A fake resolver + monkeypatched DAZZLE_CONNECTION_SECRET exercise the token
(unforgeable, per-pair) and the verify flow (TXT match → verified, uniqueness,
fail-closed) without DNS or dnspython.
"""

import base64
from datetime import datetime

import pytest

from dazzle.http.runtime.auth.connection_crypto import ConnectionSecretError
from dazzle.http.runtime.auth.connections import ConnectionRecord
from dazzle.http.runtime.auth.domain_verification import (
    DomainVerificationError,
    txt_record,
    verification_token,
    verify_domain,
)


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(b"k" * 32).decode())


def _conn(cid="conn-1", *, verified=None, domains=None) -> ConnectionRecord:
    return ConnectionRecord(
        id=cid,
        tenant_id="org-1",
        type="oidc",
        provider="native",
        domains=domains or [],
        verified_domains=verified or [],
        config={},
        secrets={},
        group_mapping={},
        status="active",
        created_at=datetime(2026, 6, 6),
        updated_at=datetime(2026, 6, 6),
    )


class _Store:
    def __init__(self, *, owner_of=None):
        # owner_of: dict domain → ConnectionRecord already verifying it
        self._owner_of = owner_of or {}
        self.claim_calls: list[tuple[str, str]] = []
        # When set, claim_verified_domain returns this regardless of owner_of —
        # simulates an atomic conflict that the (non-authoritative) fast pre-check missed.
        self.force_claim_result: bool | None = None

    def get_connection_by_verified_domain(self, domain):
        return self._owner_of.get(domain.strip().lower())

    def claim_verified_domain(self, connection_id, domain):
        norm = domain.strip().lower()
        if self.force_claim_result is not None:
            return self.force_claim_result
        owner = self._owner_of.get(norm)
        if owner is not None and owner.id != connection_id:
            return False
        self.claim_calls.append((connection_id, norm))
        self._owner_of[norm] = _conn(connection_id)
        return True


class _Resolver:
    def __init__(self, records_by_domain=None):
        self._records = records_by_domain or {}

    def resolve_txt(self, domain):
        return self._records.get(domain.strip().lower(), [])


# ---- token ----


def test_token_is_deterministic() -> None:
    assert verification_token("conn-1", "acme.test") == verification_token("conn-1", "acme.test")


def test_token_differs_per_connection_and_domain() -> None:
    a = verification_token("conn-1", "acme.test")
    assert a != verification_token("conn-2", "acme.test")  # per connection
    assert a != verification_token("conn-1", "other.test")  # per domain


def test_token_normalizes_domain() -> None:
    assert verification_token("conn-1", "ACME.test.") == verification_token("conn-1", "acme.test")


def test_txt_record_format() -> None:
    rec = txt_record("conn-1", "acme.test")
    assert rec.startswith("dazzle-verify=") and len(rec) > len("dazzle-verify=")


def test_token_fail_closed_without_key(monkeypatch) -> None:
    monkeypatch.delenv("DAZZLE_CONNECTION_SECRET", raising=False)
    with pytest.raises(ConnectionSecretError):
        verification_token("conn-1", "acme.test")


# ---- verify_domain ----


def test_verify_success_claims_domain() -> None:
    conn = _conn(verified=["already.test"])
    rec = txt_record(conn.id, "acme.test")
    store = _Store()
    resolver = _Resolver({"acme.test": ["unrelated", rec]})
    assert verify_domain(store, conn, "acme.test", resolver=resolver) is True
    assert store.claim_calls == [("conn-1", "acme.test")]  # atomic claim invoked


def test_verify_missing_txt_returns_false() -> None:
    conn = _conn()
    store = _Store()
    resolver = _Resolver({"acme.test": ["some-other-record"]})
    assert verify_domain(store, conn, "acme.test", resolver=resolver) is False
    assert store.claim_calls == []  # nothing claimed


def test_verify_wrong_token_returns_false() -> None:
    conn = _conn()
    # A token for a DIFFERENT connection must not verify this one.
    foreign = txt_record("conn-other", "acme.test")
    store = _Store()
    resolver = _Resolver({"acme.test": [foreign]})
    assert verify_domain(store, conn, "acme.test", resolver=resolver) is False
    assert store.claim_calls == []


def test_verify_already_owned_by_another_connection_raises() -> None:
    # Caught by the fast pre-check (get_connection_by_verified_domain).
    conn = _conn("conn-1")
    other = _conn("conn-2")
    store = _Store(owner_of={"acme.test": other})
    rec = txt_record(conn.id, "acme.test")
    resolver = _Resolver({"acme.test": [rec]})
    with pytest.raises(DomainVerificationError) as ei:
        verify_domain(store, conn, "acme.test", resolver=resolver)
    assert ei.value.reason == "already_verified_elsewhere"
    assert store.claim_calls == []  # never stole the domain


def test_verify_atomic_claim_conflict_raises() -> None:
    # The fast pre-check passes (no known owner), but the atomic claim loses the race
    # to a concurrent verification — verify_domain must surface the conflict, not a
    # false success.
    conn = _conn("conn-1")
    store = _Store()
    store.force_claim_result = False  # claim_verified_domain reports a conflict
    rec = txt_record(conn.id, "acme.test")
    resolver = _Resolver({"acme.test": [rec]})
    with pytest.raises(DomainVerificationError) as ei:
        verify_domain(store, conn, "acme.test", resolver=resolver)
    assert ei.value.reason == "already_verified_elsewhere"


def test_reverify_same_connection_is_idempotent() -> None:
    conn = _conn("conn-1", verified=["acme.test"])
    store = _Store(owner_of={"acme.test": conn})  # same connection already owns it
    rec = txt_record(conn.id, "acme.test")
    resolver = _Resolver({"acme.test": [rec]})
    # Fast pre-check sees the same connection (no raise); claim is idempotent-True.
    assert verify_domain(store, conn, "acme.test", resolver=resolver) is True


def test_verify_normalizes_domain_input() -> None:
    conn = _conn()
    rec = txt_record(conn.id, "acme.test")
    store = _Store()
    resolver = _Resolver({"acme.test": [rec]})
    # Caller passes mixed-case + trailing dot; the claim sees the normalized form.
    assert verify_domain(store, conn, "ACME.test.", resolver=resolver) is True
    assert store.claim_calls == [("conn-1", "acme.test")]
