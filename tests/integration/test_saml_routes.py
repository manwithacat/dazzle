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
        self.killed_memberships: list[str] = []
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

    def delete_sessions_for_membership(self, membership_id):
        self.killed_memberships.append(membership_id)


class _FakeProvider:
    def __init__(
        self,
        *,
        asserted: AssertedIdentity | None = None,
        callback_error: Exception | None = None,
        logout=None,
        logout_error: Exception | None = None,
    ):
        self._asserted = asserted
        self._callback_error = callback_error
        self._logout = logout
        self._logout_error = logout_error

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

    def process_logout(self, connection, request):
        if self._logout_error is not None:
            raise self._logout_error
        return self._logout


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


# ---- Single Logout / SLS (#1342 feature A) ----


def _seed_user_in_two_orgs(store: _Store) -> _User:
    # A user with memberships in org-1 (the SAML conn's org) AND org-2 (a foreign org).
    user = store.create_user(email="jane@acme.test", password="x")
    store._memberships.append(_Membership("mem-org1", "org-1", user.id))
    store._memberships.append(_Membership("mem-org2", "org-2", user.id))
    return user


def test_sls_kills_only_the_connections_org_sessions(saml_provider) -> None:
    from dazzle.back.runtime.auth.saml_provider import SamlLogout

    store = _Store(connections=[_conn()])  # conn-1 is in org-1
    _seed_user_in_two_orgs(store)
    saml_provider(
        _FakeProvider(
            logout=SamlLogout(name_id="jane@acme.test", redirect_url="https://idp.example/slo?x")
        )
    )
    r = _client(store).get(
        "/auth/saml/sls?connection=conn-1&SAMLRequest=abc", follow_redirects=False
    )
    assert r.status_code == 303
    # Org-scoped: only the org-1 membership's sessions are killed, NOT the foreign org-2 one.
    assert store.killed_memberships == ["mem-org1"]


def test_sls_validation_error_kills_nothing(saml_provider) -> None:
    store = _Store(connections=[_conn()])
    _seed_user_in_two_orgs(store)
    saml_provider(_FakeProvider(logout_error=ConnectionError("forged logout request")))
    r = _client(store).get(
        "/auth/saml/sls?connection=conn-1&SAMLRequest=forged", follow_redirects=False
    )
    assert r.status_code == 400
    assert store.killed_memberships == []  # fail-closed: a bad signature touches nothing


def test_sls_no_redirect_returns_200(saml_provider) -> None:
    from dazzle.back.runtime.auth.saml_provider import SamlLogout

    store = _Store(connections=[_conn()])
    _seed_user_in_two_orgs(store)
    saml_provider(_FakeProvider(logout=SamlLogout(name_id="jane@acme.test", redirect_url=None)))
    r = _client(store).get(
        "/auth/saml/sls?connection=conn-1&SAMLRequest=abc", follow_redirects=False
    )
    assert r.status_code == 200
    assert store.killed_memberships == ["mem-org1"]


def test_sls_unresolvable_connection_is_400(saml_provider) -> None:
    store = _Store(connections=[_conn()])
    saml_provider(_FakeProvider())
    r = _client(store).get("/auth/saml/sls?connection=nope&SAMLRequest=abc", follow_redirects=False)
    assert r.status_code == 400


def test_sls_unknown_email_kills_nothing(saml_provider) -> None:
    from dazzle.back.runtime.auth.saml_provider import SamlLogout

    store = _Store(connections=[_conn()])  # no users seeded
    saml_provider(_FakeProvider(logout=SamlLogout(name_id="ghost@acme.test", redirect_url=None)))
    r = _client(store).get(
        "/auth/saml/sls?connection=conn-1&SAMLRequest=abc", follow_redirects=False
    )
    assert r.status_code == 200  # idempotent no-op, no enumeration signal
    assert store.killed_memberships == []


def test_sls_oversized_saml_request_is_rejected_before_processing(saml_provider) -> None:
    # A huge SAMLRequest is rejected by the length gate BEFORE python3-saml decompresses it
    # (zip-bomb DoS guard) — the provider is never even called.
    from dazzle.back.runtime.auth.saml_provider import SamlLogout

    store = _Store(connections=[_conn()])
    _seed_user_in_two_orgs(store)
    called: list = []

    class _SpyProvider(_FakeProvider):
        def process_logout(self, connection, request):
            called.append(1)
            return SamlLogout(name_id="jane@acme.test", redirect_url=None)

    saml_provider(_SpyProvider())
    huge = "A" * 20000  # > _MAX_SAML_REQUEST_B64 (16384)
    r = _client(store).get(
        f"/auth/saml/sls?connection=conn-1&SAMLRequest={huge}", follow_redirects=False
    )
    assert r.status_code == 400
    assert called == []  # never reached the provider / decompress
    assert store.killed_memberships == []


# ---- SP-initiated completion: inbound LogoutResponse (#1342) ----


def test_sls_logout_response_completes_without_kill(saml_provider) -> None:
    from dazzle.back.runtime.auth.saml_provider import SamlLogout

    store = _Store(connections=[_conn()])
    _seed_user_in_two_orgs(store)
    # A LogoutResponse carries no NameID → no kill; just land logged-out.
    saml_provider(_FakeProvider(logout=SamlLogout(name_id=None, redirect_url=None)))
    r = _client(store).get(
        "/auth/saml/sls?connection=conn-1&SAMLResponse=abc", follow_redirects=False
    )
    assert r.status_code == 200
    assert store.killed_memberships == []


def test_sls_logout_response_error_does_not_400_the_returning_user(saml_provider) -> None:
    # The user is already locally logged out; a response-validation error must NOT 400 them.
    store = _Store(connections=[_conn()])
    saml_provider(_FakeProvider(logout_error=ConnectionError("bad logout response")))
    r = _client(store).get(
        "/auth/saml/sls?connection=conn-1&SAMLResponse=abc", follow_redirects=False
    )
    assert r.status_code == 200  # lenient on a returning LogoutResponse
    assert store.killed_memberships == []


def test_sls_forged_logout_request_still_400s(saml_provider) -> None:
    # Symmetry check: an inbound LogoutRequest (not response) that errors is STILL a 400.
    store = _Store(connections=[_conn()])
    _seed_user_in_two_orgs(store)
    saml_provider(_FakeProvider(logout_error=ConnectionError("forged request")))
    r = _client(store).get(
        "/auth/saml/sls?connection=conn-1&SAMLRequest=forged", follow_redirects=False
    )
    assert r.status_code == 400
    assert store.killed_memberships == []


def test_sls_oversized_logout_response_is_rejected(saml_provider) -> None:
    store = _Store(connections=[_conn()])
    saml_provider(_FakeProvider())
    huge = "A" * 20000
    r = _client(store).get(
        f"/auth/saml/sls?connection=conn-1&SAMLResponse={huge}", follow_redirects=False
    )
    assert r.status_code == 400


# ---- Tier 2: real-crypto IdP double (no infra; exercises the actual signature path) ----


def _idp_double_conn(idp):
    return _conn(
        config={
            "idp_entity_id": idp.entity_id,
            "idp_sso_url": "https://idp.example/sso",
            "idp_x509_cert": idp.idp_cert,
            "idp_slo_url": idp.slo_url,
        }
    )


def test_idp_double_message_validates_against_real_process_slo() -> None:
    # Foundational proof: a double-minted SIGNED LogoutRequest passes the SP's REAL process_slo
    # (signature validated for real). Pins the double's Redirect-binding encoding.
    pytest.importorskip("onelogin")
    from dazzle.back.runtime.auth.saml_provider import NativeSAMLProvider
    from tests.integration.saml_idp_double import FakeSlsRequest, SamlIdpDouble

    sls = "https://app.test/auth/saml/sls"
    idp = SamlIdpDouble(entity_id="https://idp.example/entity", slo_url="https://idp.example/slo")
    conn = _idp_double_conn(idp)
    req = FakeSlsRequest(
        idp.signed_logout_request(name_id="jane@acme.test", sp_sls_url=sls),
        base_url="https://app.test/",
    )
    out = NativeSAMLProvider().process_logout(conn, req)
    assert out.name_id == "jane@acme.test"


def test_idp_double_tampered_signature_is_rejected() -> None:
    pytest.importorskip("onelogin")
    from dazzle.back.runtime.auth.saml_provider import NativeSAMLProvider
    from tests.integration.saml_idp_double import FakeSlsRequest, SamlIdpDouble

    sls = "https://app.test/auth/saml/sls"
    idp = SamlIdpDouble(entity_id="https://idp.example/entity", slo_url="https://idp.example/slo")
    conn = _idp_double_conn(idp)
    p = idp.signed_logout_request(name_id="jane@acme.test", sp_sls_url=sls)
    p["Signature"] = ("B" if p["Signature"][0] != "B" else "C") + p["Signature"][1:]  # flip a byte
    with pytest.raises(ConnectionError):
        NativeSAMLProvider().process_logout(conn, FakeSlsRequest(p, base_url="https://app.test/"))


def test_sls_real_signed_logout_request_kills_org_sessions(saml_provider) -> None:
    # Retro-hardens feature A: a GENUINELY-signed IdP LogoutRequest through the real route +
    # real provider → org-scoped kill fires (the seam-faked A tests can't prove the crypto).
    pytest.importorskip("onelogin")
    from dazzle.back.runtime.auth.saml_provider import NativeSAMLProvider
    from tests.integration.saml_idp_double import SamlIdpDouble

    idp = SamlIdpDouble(entity_id="https://idp.example/entity", slo_url="https://idp.example/slo")
    store = _Store(connections=[_idp_double_conn(idp)])
    _seed_user_in_two_orgs(store)
    saml_provider(NativeSAMLProvider())  # the REAL provider, not a fake
    client = _client(store, base_url="https://app.test")
    params = idp.signed_logout_request(
        name_id="jane@acme.test", sp_sls_url="https://app.test/auth/saml/sls"
    )
    r = client.get(
        "/auth/saml/sls", params={"connection": "conn-1", **params}, follow_redirects=False
    )
    assert r.status_code in (200, 303)
    assert store.killed_memberships == ["mem-org1"]  # only the connection's org


def test_sls_real_signed_logout_response_completes_no_kill(saml_provider) -> None:
    pytest.importorskip("onelogin")
    from dazzle.back.runtime.auth.saml_provider import NativeSAMLProvider
    from tests.integration.saml_idp_double import SamlIdpDouble

    idp = SamlIdpDouble(entity_id="https://idp.example/entity", slo_url="https://idp.example/slo")
    store = _Store(connections=[_idp_double_conn(idp)])
    _seed_user_in_two_orgs(store)
    saml_provider(NativeSAMLProvider())
    client = _client(store, base_url="https://app.test")
    params = idp.signed_logout_response(
        in_response_to="_req123", sp_sls_url="https://app.test/auth/saml/sls"
    )
    r = client.get(
        "/auth/saml/sls", params={"connection": "conn-1", **params}, follow_redirects=False
    )
    assert r.status_code in (200, 303)
    assert store.killed_memberships == []  # a response performs no kill


def test_sls_both_request_and_response_is_rejected(saml_provider) -> None:
    # Ambiguous: a legit SLO message is never both. Reject outright (don't rely on library
    # precedence) — and a forged LogoutRequest hidden behind a SAMLResponse kills nothing.
    store = _Store(connections=[_conn()])
    _seed_user_in_two_orgs(store)
    saml_provider(_FakeProvider())  # must never be reached
    r = _client(store).get(
        "/auth/saml/sls?connection=conn-1&SAMLRequest=forged&SAMLResponse=x",
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert store.killed_memberships == []
