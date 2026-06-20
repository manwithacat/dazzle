"""Enterprise SSO route tests (auth Plan 4b.iii).

A fake ConnectionProvider (registered for the (oidc, native) seam) drives the
initiate/callback without authlib or a real IdP; the join logic
(``provision_enterprise_login``) runs for real against a fake AuthStore. This
exercises the route wiring + session-fixation + cookie binding + error mapping.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from dazzle.http.runtime.auth.connections import (
    AssertedIdentity,
    ConnectionRecord,
    register_provider,
)
from dazzle.http.runtime.auth.enterprise_routes import create_enterprise_sso_routes


def _conn(**over) -> ConnectionRecord:
    base = {
        "id": "conn-1",
        "tenant_id": "org-1",
        "type": "oidc",
        "provider": "native",
        "domains": ["acme.test"],
        "verified_domains": ["acme.test"],
        "config": {},
        "secrets": {},
        "group_mapping": {},
        "status": "active",
        "created_at": datetime(2026, 6, 5),
        "updated_at": datetime(2026, 6, 5),
    }
    base.update(over)
    return ConnectionRecord(**base)


class _User:
    def __init__(self, uid: str, email: str, verified: bool = True):
        self.id = uid
        self.email = email
        self.email_verified = verified
        self.roles: list[str] = []


class _Membership:
    def __init__(self, mid: str, tenant_id: str, identity_id: str):
        self.id = mid
        self.tenant_id = tenant_id
        self.identity_id = identity_id
        self.status = "active"


class _Session:
    def __init__(self, sid: str):
        self.id = sid
        self.csrf_secret = f"csrf-{sid}"


class _Store:
    def __init__(self, *, connections=None):
        self._connections = {c.id: c for c in (connections or [])}
        self._users: dict[str, _User] = {}
        self._memberships: list[_Membership] = []
        self.created_sessions: list[str] = []
        self.deleted_sessions: list[str] = []
        self._n = 0

    # --- connections ---
    def get_connection(self, connection_id, *, tenant_id=None):
        return self._connections.get(connection_id)

    def get_connection_by_verified_domain(self, domain):
        d = domain.strip().lower()
        for c in self._connections.values():
            if c.status == "active" and d in {x.lower() for x in c.verified_domains}:
                return c
        return None

    def get_connections_for_tenant(self, tenant_id):
        return [c for c in self._connections.values() if c.tenant_id == tenant_id]

    # --- identities / memberships (back provision_enterprise_login) ---
    def get_user_by_email(self, email):
        return self._users.get(email)

    def create_user(self, *, email, password, username=None):
        self._n += 1
        u = _User(f"uid-{self._n}", email)
        self._users[email] = u
        return u

    def mark_email_verified(self, user_id):
        return True

    def get_memberships_for_identity(self, identity_id):
        return [m for m in self._memberships if m.identity_id == identity_id]

    def create_membership(self, *, tenant_id, identity_id, roles=None, reason=None):
        m = _Membership(f"mem-{self._n}", tenant_id, identity_id)
        self._memberships.append(m)
        return m

    # --- sessions ---
    def create_session(self, user, *, active_membership_id=None):
        self._n += 1
        sid = f"sess-{self._n}"
        self.created_sessions.append(sid)
        self._last_active_membership = active_membership_id
        return _Session(sid)

    def delete_session(self, sid):
        self.deleted_sessions.append(sid)


class _FakeProvider:
    """Registered for (oidc, native); bypasses authlib."""

    def __init__(self, *, asserted: AssertedIdentity | None = None):
        self._asserted = asserted

    async def initiate(self, connection, request):
        return f"https://idp.example/authorize?conn={connection.id}"

    async def callback(self, connection, request):
        return self._asserted or AssertedIdentity(email="jane@acme.test")


@pytest.fixture
def fake_provider():
    """Register a fake (oidc, native) provider, restoring the registry after."""
    from dazzle.http.runtime.auth.connections import _PROVIDERS

    holder: dict[str, _FakeProvider] = {}

    def _install(provider: _FakeProvider) -> None:
        holder["p"] = provider
        register_provider("oidc", "native", provider)

    try:
        yield _install
    finally:
        _PROVIDERS.pop(("oidc", "native"), None)


def _client(store: _Store) -> TestClient:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret", same_site="lax")
    app.include_router(create_enterprise_sso_routes())
    app.state.auth_store = store
    return TestClient(app)


# ---- login ----


def test_login_redirects_to_idp_and_stashes_connection(fake_provider) -> None:
    fake_provider(_FakeProvider())
    store = _Store(connections=[_conn()])
    client = _client(store)
    r = client.get("/auth/enterprise/login?connection=conn-1", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "https://idp.example/authorize?conn=conn-1"


def test_login_unknown_connection_errors(fake_provider) -> None:
    fake_provider(_FakeProvider())
    client = _client(_Store(connections=[]))
    r = client.get("/auth/enterprise/login?connection=missing", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?error=sso_no_connection"


def test_login_inactive_connection_rejected(fake_provider) -> None:
    fake_provider(_FakeProvider())
    store = _Store(connections=[_conn(status="disabled")])
    r = _client(store).get("/auth/enterprise/login?connection=conn-1", follow_redirects=False)
    assert r.headers["location"] == "/login?error=sso_no_connection"


def test_login_resolves_by_verified_email_domain(fake_provider) -> None:
    fake_provider(_FakeProvider())
    store = _Store(connections=[_conn(verified_domains=["acme.test"])])
    r = _client(store).get("/auth/enterprise/login?email=jane@acme.test", follow_redirects=False)
    assert r.status_code == 303
    # host-exact check (not a substring) — the redirect must target the IdP origin
    assert urlparse(r.headers["location"]).hostname == "idp.example"


# ---- callback ----


def test_callback_success_mints_session_and_cookies(fake_provider) -> None:
    fake_provider(_FakeProvider(asserted=AssertedIdentity(email="jane@acme.test")))
    store = _Store(connections=[_conn(verified_domains=["acme.test"])])
    client = _client(store)
    # login first to stash the connection id in the session cookie
    client.get("/auth/enterprise/login?connection=conn-1", follow_redirects=False)
    r = client.get("/auth/enterprise/callback", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/app"
    assert store.created_sessions  # a session was minted
    cookies = r.headers.get_list("set-cookie")
    assert any("dazzle_session=" in c for c in cookies)
    assert any("dazzle_csrf=" in c for c in cookies)


def test_callback_without_stashed_connection_fails(fake_provider) -> None:
    fake_provider(_FakeProvider())
    r = _client(_Store(connections=[_conn()])).get(
        "/auth/enterprise/callback", follow_redirects=False
    )
    assert r.headers["location"] == "/login?error=sso_failed"


def test_callback_join_refused_maps_reason(fake_provider) -> None:
    # Asserted email outside the connection's verified domains → domain_not_verified.
    fake_provider(_FakeProvider(asserted=AssertedIdentity(email="eve@evil.test")))
    store = _Store(connections=[_conn(verified_domains=["acme.test"])])
    client = _client(store)
    client.get("/auth/enterprise/login?connection=conn-1", follow_redirects=False)
    r = client.get("/auth/enterprise/callback", follow_redirects=False)
    assert r.headers["location"] == "/login?error=sso_domain_not_verified"
    assert not store.created_sessions  # no session for a refused join


def test_callback_session_fixation_deletes_pre_auth_sid(fake_provider) -> None:
    fake_provider(_FakeProvider(asserted=AssertedIdentity(email="jane@acme.test")))
    store = _Store(connections=[_conn(verified_domains=["acme.test"])])
    client = _client(store)
    client.get("/auth/enterprise/login?connection=conn-1", follow_redirects=False)
    # Present a pre-auth session cookie; it must be invalidated on success.
    client.cookies.set("dazzle_session", "attacker-planted-sid")
    r = client.get("/auth/enterprise/callback", follow_redirects=False)
    assert r.status_code == 303
    assert "attacker-planted-sid" in store.deleted_sessions
