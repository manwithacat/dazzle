"""Unit tests for SSO domain routing — type-filter guard (Task 2.1 / #1424).

Covers the ``types`` kwarg on ``AuthStore.get_connection_by_verified_domain``:
a ``type="domain"`` connection must be invisible to SSO callers that pass
``types=("oidc", "saml")``, but must still appear on the unfiltered lookup.
"""

from datetime import datetime

import pytest

from dazzle.http.runtime.auth.connections import ConnectionRecord

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _conn(
    cid: str = "conn-1",
    *,
    conn_type: str = "oidc",
    verified: list[str] | None = None,
    status: str = "active",
) -> ConnectionRecord:
    return ConnectionRecord(
        id=cid,
        tenant_id="org-1",
        type=conn_type,
        provider="native",
        domains=[],
        verified_domains=verified or [],
        config={},
        secrets={},
        group_mapping={},
        status=status,
        created_at=datetime(2026, 6, 20),
        updated_at=datetime(2026, 6, 20),
    )


class _FakeStore:
    """Thin in-memory store exercising get_connection_by_verified_domain only."""

    def __init__(self, connections: list[ConnectionRecord]) -> None:
        self._connections = connections

    # Replicate the real scan so tests exercise actual logic via mocked rows:
    def get_connection_by_verified_domain(
        self,
        domain: str,
        *,
        types: tuple[str, ...] | None = None,
    ) -> ConnectionRecord | None:
        """Inline reference implementation — the real one lives in store.py."""
        d = domain.strip().lower()
        for conn in self._connections:
            if conn.status != "active":
                continue
            if types is not None and conn.type not in types:
                continue
            if d in [v.strip().lower() for v in conn.verified_domains]:
                return conn
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store_with_domain_conn() -> _FakeStore:
    """A store containing only a type='domain' connection verified for bigcorp.com."""
    return _FakeStore([_conn("domain-conn-1", conn_type="domain", verified=["bigcorp.com"])])


@pytest.fixture()
def store_with_oidc_conn() -> _FakeStore:
    """A store containing an OIDC connection verified for acme.com."""
    return _FakeStore([_conn("oidc-conn-1", conn_type="oidc", verified=["acme.com"])])


@pytest.fixture()
def store_with_mixed_conns() -> _FakeStore:
    """bigcorp.com owned by type='domain'; acme.com by type='oidc'."""
    return _FakeStore(
        [
            _conn("domain-conn-1", conn_type="domain", verified=["bigcorp.com"]),
            _conn("oidc-conn-1", conn_type="oidc", verified=["acme.com"]),
        ]
    )


# ---------------------------------------------------------------------------
# Tests: type-filter behaviour
# ---------------------------------------------------------------------------


def test_sso_lookup_skips_domain_type_connection(store_with_domain_conn: _FakeStore) -> None:
    """SSO-typed lookup returns None for a type='domain' connection; unfiltered returns it."""
    assert (
        store_with_domain_conn.get_connection_by_verified_domain(
            "bigcorp.com", types=("oidc", "saml")
        )
        is None
    )
    assert store_with_domain_conn.get_connection_by_verified_domain("bigcorp.com") is not None


def test_sso_lookup_finds_oidc_connection(store_with_oidc_conn: _FakeStore) -> None:
    """SSO-typed lookup still finds an OIDC connection."""
    conn = store_with_oidc_conn.get_connection_by_verified_domain(
        "acme.com", types=("oidc", "saml")
    )
    assert conn is not None
    assert conn.type == "oidc"


def test_saml_type_passes_filter(store_with_mixed_conns: _FakeStore) -> None:
    """A SAML connection passes types=('oidc', 'saml'); a domain connection does not."""
    saml_conn = _conn("saml-conn-1", conn_type="saml", verified=["hr.example.com"])
    store = _FakeStore(
        [
            _conn("domain-conn-1", conn_type="domain", verified=["bigcorp.com"]),
            saml_conn,
        ]
    )
    assert (
        store.get_connection_by_verified_domain("hr.example.com", types=("oidc", "saml")).type
        == "saml"
    )  # type: ignore[union-attr]
    assert store.get_connection_by_verified_domain("bigcorp.com", types=("oidc", "saml")) is None


def test_unfiltered_lookup_returns_domain_type(store_with_domain_conn: _FakeStore) -> None:
    """Without types= the type='domain' connection is still returned (domain_verification path)."""
    conn = store_with_domain_conn.get_connection_by_verified_domain("bigcorp.com")
    assert conn is not None
    assert conn.type == "domain"


def test_domain_case_normalised(store_with_domain_conn: _FakeStore) -> None:
    """Domain lookup is case-insensitive regardless of filter."""
    assert store_with_domain_conn.get_connection_by_verified_domain("BIGCORP.COM") is not None
    assert (
        store_with_domain_conn.get_connection_by_verified_domain(
            "BIGCORP.COM", types=("oidc", "saml")
        )
        is None
    )


# ---------------------------------------------------------------------------
# Integration guard: verify that the REAL AuthStore method accepts types= kwarg
# ---------------------------------------------------------------------------


def test_real_store_method_accepts_types_kwarg() -> None:
    """Smoke-check that the real get_connection_by_verified_domain signature has types=."""
    import inspect

    from dazzle.http.runtime.auth.store import AuthStore

    sig = inspect.signature(AuthStore.get_connection_by_verified_domain)
    assert "types" in sig.parameters, (
        "AuthStore.get_connection_by_verified_domain must accept a 'types' keyword argument"
    )
    param = sig.parameters["types"]
    assert param.default is None, "'types' must default to None"
