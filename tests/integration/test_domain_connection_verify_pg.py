"""Regression guard: a domain-type connection verifies via the DNS-TXT flow (#1424 phase 2).

This test proves the provider-less ``type="domain"`` connection reuses the existing
``verify_domain`` / ``claim_verified_domain`` machinery end-to-end on real Postgres,
and that the one-owner-per-domain guarantee is enforced at the store level.
"""

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
    scratch = f"dazzle_domver_{uuid.uuid4().hex[:8]}"
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
    from dazzle.http.runtime.auth.store import AuthStore

    s = AuthStore(database_url=store_url)
    s._init_db()
    return s


class _FakeResolver:
    """Injected resolver returning a fixed mapping of domain → TXT records."""

    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self._m = mapping

    def resolve_txt(self, domain: str) -> list[str]:
        return self._m.get(domain, [])


# ---------------------------------------------------------------------------
# Test 1: happy path — domain-type connection verifies via DNS-TXT
# ---------------------------------------------------------------------------


def test_domain_connection_verifies(store_url: str) -> None:
    from dazzle.http.runtime.auth.domain_verification import txt_record, verify_domain

    store = _store(store_url)
    org = store.create_organization(slug="acme", name="Acme")
    conn = store.create_connection(
        tenant_id=org.id,
        type="domain",
        config={},
        secrets={},
        domains=["bigcorp.com"],
    )

    resolver = _FakeResolver({"bigcorp.com": [txt_record(conn.id, "bigcorp.com")]})
    result = verify_domain(store, conn, "bigcorp.com", resolver=resolver)

    assert result is True

    refreshed = store.get_connection(conn.id)
    assert refreshed is not None
    assert "bigcorp.com" in refreshed.verified_domains


# ---------------------------------------------------------------------------
# Test 2: one-owner-per-domain — a second connection cannot claim the same domain
# ---------------------------------------------------------------------------


def test_domain_connection_one_owner_per_domain(store_url: str) -> None:
    from dazzle.http.runtime.auth.domain_verification import (
        DomainVerificationError,
        txt_record,
        verify_domain,
    )

    store = _store(store_url)
    org = store.create_organization(slug="bigco", name="BigCo")

    conn1 = store.create_connection(
        tenant_id=org.id,
        type="domain",
        config={},
        secrets={},
        domains=["bigcorp.com"],
    )
    conn2 = store.create_connection(
        tenant_id=org.id,
        type="domain",
        config={},
        secrets={},
        domains=["bigcorp.com"],
    )

    # conn1 verifies successfully.
    resolver1 = _FakeResolver({"bigcorp.com": [txt_record(conn1.id, "bigcorp.com")]})
    assert verify_domain(store, conn1, "bigcorp.com", resolver=resolver1) is True

    # conn2's TXT record is correct for conn2 but the domain is already owned by conn1.
    resolver2 = _FakeResolver({"bigcorp.com": [txt_record(conn2.id, "bigcorp.com")]})
    with pytest.raises(DomainVerificationError) as exc_info:
        verify_domain(store, conn2, "bigcorp.com", resolver=resolver2)

    assert exc_info.value.reason == "already_verified_elsewhere"

    # The domain must NOT appear in conn2's verified list.
    refreshed2 = store.get_connection(conn2.id)
    assert refreshed2 is not None
    assert "bigcorp.com" not in (refreshed2.verified_domains or [])
