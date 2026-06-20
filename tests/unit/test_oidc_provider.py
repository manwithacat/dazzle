"""NativeOIDCProvider unit tests (auth Plan 4b.i).

The authlib client is faked (pre-seeded into the provider's per-connection
cache) so these run without authlib installed and without real network/IdP —
they pin the provider's identity-level invariants, not authlib's token crypto.
"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.auth.connections import (
    AssertedIdentity,
    ConnectionError,
    ConnectionRecord,
    resolve_provider,
)
from dazzle.http.runtime.auth.oidc_provider import (
    NativeOIDCProvider,
    _coerce_groups,
    register_native_oidc,
)


def _conn(**over) -> ConnectionRecord:
    base = {
        "id": "conn-1",
        "tenant_id": "org-1",
        "type": "oidc",
        "provider": "native",
        "domains": [],
        "verified_domains": [],
        "config": {"client_id": "cid", "issuer": "https://idp.example"},
        "secrets": {"client_secret": "shh"},
        "group_mapping": {},
        "status": "active",
        "created_at": datetime(2026, 6, 5),
        "updated_at": datetime(2026, 6, 5),
    }
    base.update(over)
    return ConnectionRecord(**base)


class _FakeClient:
    """Stands in for an authlib StarletteOAuth2App."""

    def __init__(self, *, location="https://idp.example/authorize?x=1", token=None, userinfo=None):
        self._location = location
        self._token = token if token is not None else {}
        self._userinfo = userinfo
        self.seen_callback: str | None = None

    async def authorize_redirect(self, request, callback_url):
        self.seen_callback = callback_url
        return SimpleNamespace(headers={"location": self._location})

    async def authorize_access_token(self, request):
        return self._token

    async def userinfo(self, token):
        return self._userinfo or {}


def _provider_with(client: _FakeClient, conn: ConnectionRecord) -> NativeOIDCProvider:
    p = NativeOIDCProvider()
    # Seed the (revision, client) cache entry so _client returns the fake and
    # never reaches the authlib import.
    p._clients[conn.id] = (p._revision(conn), client)
    return p


_REQ = SimpleNamespace(base_url="https://app.test/")


# ---- config validation (no authlib needed; raises before the lazy import) ----


def test_missing_client_id_raises() -> None:
    p = NativeOIDCProvider()
    conn = _conn(config={"issuer": "https://idp.example"})  # no client_id
    with pytest.raises(ConnectionError, match="client_id"):
        p._client(conn)


def test_missing_discovery_and_issuer_raises() -> None:
    p = NativeOIDCProvider()
    conn = _conn(config={"client_id": "cid"})  # no issuer/discovery_url
    with pytest.raises(ConnectionError, match="discovery_url or config.issuer"):
        p._client(conn)


def test_client_cache_hit_same_revision() -> None:
    conn = _conn()
    sentinel = object()
    p = NativeOIDCProvider()
    p._clients[conn.id] = (p._revision(conn), sentinel)
    assert p._client(conn) is sentinel  # same updated_at → reuse


def test_client_rebuilds_when_revision_changes() -> None:
    # A rotated secret / repointed issuer bumps updated_at; the stale cached
    # client must NOT be reused. We prove the rebuild branch runs by rotating to
    # a config that fails validation (raises before the authlib import) — a stale
    # cache-hit would have returned the sentinel instead of raising.
    conn = _conn()
    sentinel = object()
    p = NativeOIDCProvider()
    p._clients[conn.id] = (p._revision(conn), sentinel)
    rotated = _conn(updated_at=datetime(2026, 7, 1), config={"issuer": "https://idp.example"})
    with pytest.raises(ConnectionError, match="client_id"):
        p._client(rotated)


# ---- initiate ----


async def test_initiate_returns_authorize_url_and_uses_stable_callback() -> None:
    conn = _conn()
    client = _FakeClient(location="https://idp.example/authorize?state=abc")
    p = _provider_with(client, conn)
    url = await p.initiate(conn, _REQ)
    assert url == "https://idp.example/authorize?state=abc"
    # One stable redirect URI per app, derived from request.base_url.
    assert client.seen_callback == "https://app.test/auth/enterprise/callback"


# ---- callback ----


async def test_callback_maps_userinfo_to_asserted_identity() -> None:
    conn = _conn()
    client = _FakeClient(
        token={
            "userinfo": {
                "email": "Jane@Acme.test",
                "email_verified": True,
                "groups": ["eng", "admins"],
            }
        }
    )
    p = _provider_with(client, conn)
    asserted = await p.callback(conn, _REQ)
    assert isinstance(asserted, AssertedIdentity)
    assert asserted.email == "jane@acme.test"  # normalized
    assert asserted.groups == ["eng", "admins"]


async def test_callback_id_token_claims_source() -> None:
    conn = _conn()
    client = _FakeClient(token={"userinfo": {"email": "x@acme.test", "email_verified": True}})
    p = _provider_with(client, conn)
    asserted = await p.callback(conn, _REQ)
    assert asserted.claims_source == "id_token"  # validated claims


async def test_callback_falls_back_to_userinfo_endpoint() -> None:
    conn = _conn()
    client = _FakeClient(token={}, userinfo={"email": "x@acme.test"})
    p = _provider_with(client, conn)
    asserted = await p.callback(conn, _REQ)
    assert asserted.email == "x@acme.test"
    # The fallback path's claims are not id_token-validated — provenance recorded
    # so 4b.ii's identity-join can apply differential trust.
    assert asserted.claims_source == "userinfo_endpoint"


async def test_callback_empty_email_refuses() -> None:
    conn = _conn()
    client = _FakeClient(token={"userinfo": {"email": "", "email_verified": True}})
    p = _provider_with(client, conn)
    with pytest.raises(ConnectionError, match="no email"):
        await p.callback(conn, _REQ)


async def test_callback_explicit_email_unverified_refuses() -> None:
    conn = _conn()
    client = _FakeClient(token={"userinfo": {"email": "x@acme.test", "email_verified": False}})
    p = _provider_with(client, conn)
    with pytest.raises(ConnectionError, match="email_verified=false"):
        await p.callback(conn, _REQ)


async def test_callback_missing_email_verified_is_tolerated() -> None:
    conn = _conn()
    client = _FakeClient(token={"userinfo": {"email": "x@acme.test"}})  # no email_verified
    p = _provider_with(client, conn)
    asserted = await p.callback(conn, _REQ)
    assert asserted.email == "x@acme.test"


async def test_callback_custom_groups_claim() -> None:
    conn = _conn(
        config={"client_id": "cid", "issuer": "https://idp.example", "groups_claim": "roles"}
    )
    client = _FakeClient(
        token={"userinfo": {"email": "x@acme.test", "roles": "manager", "groups": ["ignored"]}}
    )
    p = _provider_with(client, conn)
    asserted = await p.callback(conn, _REQ)
    assert asserted.groups == ["manager"]  # read the configured claim, not the default


# ---- group coercion ----


def test_coerce_groups_shapes() -> None:
    assert _coerce_groups(None) == []
    assert _coerce_groups("solo") == ["solo"]
    assert _coerce_groups(["a", "b"]) == ["a", "b"]
    assert _coerce_groups(["a", "", None]) == ["a"]  # drops empties/None
    assert _coerce_groups(42) == ["42"]


# ---- registration ----


def test_register_native_oidc_resolves() -> None:
    from dazzle.http.runtime.auth.connections import _PROVIDERS

    register_native_oidc()
    try:
        impl = resolve_provider(SimpleNamespace(type="oidc", provider="native"))
        assert isinstance(impl, NativeOIDCProvider)
    finally:
        _PROVIDERS.pop(("oidc", "native"), None)  # don't leak into other tests
