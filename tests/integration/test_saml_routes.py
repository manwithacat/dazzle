"""SAML SSO route tests (auth Plan 5.ii).

A fake SAML ConnectionProvider (registered for (saml, native)) drives initiate/ACS
without python3-saml or a real IdP; the JIT join (`provision_enterprise_login`) runs
for real against a fake AuthStore. Pins the route wiring, session-fixation, cookie
binding, and error mapping (the signature/InResponseTo validation is the provider's,
covered in test_saml_provider.py).
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from dazzle.back.runtime.auth.connections import (
    AssertedIdentity,
    ConnectionError,
    ConnectionRecord,
    register_provider,
)
from dazzle.back.runtime.auth.saml_routes import create_saml_routes


def _conn(**over) -> ConnectionRecord:
    base = {
        "id": "conn-1",
        "tenant_id": "org-1",
        "type": "saml",
        "provider": "native",
        "domains": ["acme.test"],
        "verified_domains": ["acme.test"],
        "config": {},
        "secrets": {},
        "group_mapping": {},
        "status": "active",
        "created_at": datetime(2026, 6, 6),
        "updated_at": datetime(2026, 6, 6),
    }
    base.update(over)
    return ConnectionRecord(**base)


class _User:
    def __init__(self, uid, email):
        self.id = uid
        self.email = email
        self.email_verified = True
        self.roles: list[str] = []


class _Membership:
    def __init__(self, mid, tenant_id, identity_id):
        self.id = mid
        self.tenant_id = tenant_id
        self.identity_id = identity_id
        self.status = "active"


class _Session:
    def __init__(self, sid):
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

    def create_session(self, user, *, active_membership_id=None):
        self._n += 1
        sid = f"sess-{self._n}"
        self.created_sessions.append(sid)
        return _Session(sid)

    def delete_session(self, sid):
        self.deleted_sessions.append(sid)


class _FakeProvider:
    def __init__(
        self, *, asserted: AssertedIdentity | None = None, callback_error: Exception | None = None
    ):
        self._asserted = asserted
        self._callback_error = callback_error

    async def initiate(self, connection, request):
        # A real provider stashes the AuthnRequest id; the route stashes the connection id.
        request.session["saml_request_id"] = "req-abc"
        return f"https://idp.example/sso?conn={connection.id}"

    async def callback(self, connection, request):
        if self._callback_error is not None:
            raise self._callback_error
        return self._asserted or AssertedIdentity(
            email="jane@acme.test", claims_source="saml_assertion"
        )


@pytest.fixture
def saml_provider():
    from dazzle.back.runtime.auth.connections import _PROVIDERS

    def _install(provider: _FakeProvider) -> None:
        register_provider("saml", "native", provider)

    try:
        yield _install
    finally:
        _PROVIDERS.pop(("saml", "native"), None)


def _client(store: _Store, *, base_url: str = "http://testserver") -> TestClient:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret", same_site="lax")
    app.include_router(create_saml_routes())
    app.state.auth_store = store
    # A valid base_url matters for real metadata generation: onelogin rejects an ACS URL
    # whose host has no TLD (the default "testserver"). Tests that build real SP metadata
    # pass a routable host.
    return TestClient(app, base_url=base_url)


def _asserted(email: str) -> AssertedIdentity:
    return AssertedIdentity(email=email, claims_source="saml_assertion")


# ---- login ----


def test_login_redirects_to_idp(saml_provider) -> None:
    saml_provider(_FakeProvider())
    store = _Store(connections=[_conn()])
    r = _client(store).get("/auth/saml/login?connection=conn-1", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "https://idp.example/sso?conn=conn-1"


def test_login_unknown_connection_errors(saml_provider) -> None:
    saml_provider(_FakeProvider())
    r = _client(_Store(connections=[])).get(
        "/auth/saml/login?connection=missing", follow_redirects=False
    )
    assert r.headers["location"] == "/login?error=sso_no_connection"


def test_login_resolves_by_verified_email_domain(saml_provider) -> None:
    saml_provider(_FakeProvider())
    store = _Store(connections=[_conn(verified_domains=["acme.test"])])
    r = _client(store).get("/auth/saml/login?email=jane@acme.test", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("https://idp.example")


# ---- ACS ----


def test_acs_success_mints_session_and_cookies(saml_provider) -> None:
    saml_provider(_FakeProvider(asserted=_asserted("jane@acme.test")))
    store = _Store(connections=[_conn(verified_domains=["acme.test"])])
    client = _client(store)
    client.get("/auth/saml/login?connection=conn-1", follow_redirects=False)  # stash conn id
    r = client.post("/auth/saml/acs", data={"SAMLResponse": "x"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/app"
    assert store.created_sessions
    cookies = r.headers.get_list("set-cookie")
    assert any("dazzle_session=" in c for c in cookies)
    assert any("dazzle_csrf=" in c for c in cookies)


def test_acs_without_stashed_connection_fails(saml_provider) -> None:
    saml_provider(_FakeProvider())
    r = _client(_Store(connections=[_conn()])).post(
        "/auth/saml/acs", data={"SAMLResponse": "x"}, follow_redirects=False
    )
    assert r.headers["location"] == "/login?error=sso_failed"


def test_acs_join_refused_maps_reason(saml_provider) -> None:
    saml_provider(_FakeProvider(asserted=_asserted("eve@evil.test")))  # outside verified domain
    store = _Store(connections=[_conn(verified_domains=["acme.test"])])
    client = _client(store)
    client.get("/auth/saml/login?connection=conn-1", follow_redirects=False)
    r = client.post("/auth/saml/acs", data={"SAMLResponse": "x"}, follow_redirects=False)
    assert r.headers["location"] == "/login?error=sso_domain_not_verified"
    assert not store.created_sessions


def test_acs_invalid_response_fails(saml_provider) -> None:
    saml_provider(_FakeProvider(callback_error=ConnectionError("bad signature")))
    store = _Store(connections=[_conn(verified_domains=["acme.test"])])
    client = _client(store)
    client.get("/auth/saml/login?connection=conn-1", follow_redirects=False)
    r = client.post("/auth/saml/acs", data={"SAMLResponse": "x"}, follow_redirects=False)
    assert r.headers["location"] == "/login?error=sso_failed"
    assert not store.created_sessions


def test_acs_session_fixation_deletes_pre_auth_sid(saml_provider) -> None:
    saml_provider(_FakeProvider(asserted=_asserted("jane@acme.test")))
    store = _Store(connections=[_conn(verified_domains=["acme.test"])])
    client = _client(store)
    client.get("/auth/saml/login?connection=conn-1", follow_redirects=False)
    client.cookies.set("dazzle_session", "attacker-planted-sid")
    r = client.post("/auth/saml/acs", data={"SAMLResponse": "x"}, follow_redirects=False)
    assert r.status_code == 303
    assert "attacker-planted-sid" in store.deleted_sessions


# ---- SP metadata (#1342) ----


def test_metadata_serves_sp_xml(monkeypatch) -> None:
    """GET /auth/saml/metadata returns the SP metadata XML with the SAML metadata
    content type (the IdP imports this)."""
    import dazzle.back.runtime.auth.saml_provider as sp

    monkeypatch.setattr(
        sp.NativeSAMLProvider,
        "sp_metadata",
        lambda self, request, connection=None: (
            "<md:EntityDescriptor entityID='https://app.test/auth/saml/acs'/>"
        ),
    )
    resp = _client(_Store()).get("/auth/saml/metadata")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/samlmetadata+xml")
    assert "EntityDescriptor" in resp.text


def test_metadata_503_when_generation_fails(monkeypatch) -> None:
    """Generation failure (e.g. [saml] extra absent) → 503, never a 500 stack leak."""
    import dazzle.back.runtime.auth.saml_provider as sp

    def _boom(self, request, connection=None):
        raise RuntimeError("python3-saml not installed")

    monkeypatch.setattr(sp.NativeSAMLProvider, "sp_metadata", _boom)
    resp = _client(_Store()).get("/auth/saml/metadata")
    assert resp.status_code == 503


def test_metadata_connection_param_advertises_signing_cert() -> None:
    """?connection=<id> with request signing on → metadata carries the signing cert."""
    pytest.importorskip("onelogin")
    from dazzle.back.runtime.auth.saml_sp_keys import generate_sp_keypair

    key, cert = generate_sp_keypair("https://app.test/auth/saml/acs")
    conn = _conn(
        id="c-sign",
        config={
            "idp_entity_id": "https://idp/e",
            "idp_sso_url": "https://idp/sso",
            "idp_x509_cert": "x",
            "sign_requests": "true",
            "sp_cert": cert,
        },
        secrets={"sp_private_key": key},
    )
    resp = _client(_Store(connections=[conn]), base_url="https://app.test").get(
        "/auth/saml/metadata?connection=c-sign"
    )
    assert resp.status_code == 200 and 'use="signing"' in resp.text
    assert "PRIVATE KEY" not in resp.text  # never the private key


def test_metadata_unknown_connection_falls_back_to_app_level() -> None:
    pytest.importorskip("onelogin")
    resp = _client(_Store(), base_url="https://app.test").get("/auth/saml/metadata?connection=nope")
    assert resp.status_code == 200 and 'use="signing"' not in resp.text
