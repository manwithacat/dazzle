"""Enterprise SSO route tests (auth Plan 4b.iii).

A fake ConnectionProvider (registered for the (oidc, native) seam) drives the
initiate/callback without authlib or a real IdP; the join logic
(``provision_enterprise_login``) runs for real against a fake AuthStore. This
exercises the route wiring + session-fixation + cookie binding + error mapping.

The ``require_sso`` section mounts the local sign-in routes (JSON and form login,
magic-link and password-reset requests) beside them and pins each refusal (DD-013).
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
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
from dazzle.http.runtime.auth.enterprise_login import ENTERPRISE_OIDC_STATE_ATTR
from dazzle.http.runtime.auth.enterprise_routes import create_enterprise_sso_routes
from dazzle.http.runtime.auth.magic_link_routes import create_magic_link_routes
from dazzle.http.runtime.auth.password_login_routes import create_password_login_routes
from dazzle.http.runtime.auth.password_reset_routes import create_password_reset_routes
from dazzle.http.runtime.auth.routes import create_auth_routes

# secrets.token_urlsafe(24) is 32 urlsafe chars (the connection-id shape).
CONN_ID = "A" * 32
UNKNOWN_CONN = "B" * 32


def _conn(**over) -> ConnectionRecord:
    base = {
        "id": CONN_ID,
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

    def get_connection_by_verified_domain(self, domain, *, types=None):
        d = domain.strip().lower()
        for c in self._connections.values():
            if (
                c.status == "active"
                and (types is None or c.type in types)
                and d in {x.lower() for x in c.verified_domains}
            ):
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
    def create_session(self, user, *, active_membership_id=None, **_kwargs):
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
    r = client.get(f"/auth/enterprise/login?connection={CONN_ID}", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"https://idp.example/authorize?conn={CONN_ID}"


def test_login_unknown_connection_errors(fake_provider) -> None:
    fake_provider(_FakeProvider())
    client = _client(_Store(connections=[]))
    r = client.get(f"/auth/enterprise/login?connection={UNKNOWN_CONN}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?error=sso_no_connection"


def test_login_inactive_connection_rejected(fake_provider) -> None:
    fake_provider(_FakeProvider())
    store = _Store(connections=[_conn(status="disabled")])
    r = _client(store).get(f"/auth/enterprise/login?connection={CONN_ID}", follow_redirects=False)
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
    client.get(f"/auth/enterprise/login?connection={CONN_ID}", follow_redirects=False)
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
    client.get(f"/auth/enterprise/login?connection={CONN_ID}", follow_redirects=False)
    r = client.get("/auth/enterprise/callback", follow_redirects=False)
    assert r.headers["location"] == "/login?error=sso_domain_not_verified"
    assert not store.created_sessions  # no session for a refused join


def test_callback_session_fixation_deletes_pre_auth_sid(fake_provider) -> None:
    fake_provider(_FakeProvider(asserted=AssertedIdentity(email="jane@acme.test")))
    store = _Store(connections=[_conn(verified_domains=["acme.test"])])
    client = _client(store)
    client.get(f"/auth/enterprise/login?connection={CONN_ID}", follow_redirects=False)
    # Present a pre-auth session cookie; it must be invalidated on success.
    client.cookies.set("dazzle_session", "attacker-planted-sid")
    r = client.get("/auth/enterprise/callback", follow_redirects=False)
    assert r.status_code == 303
    assert "attacker-planted-sid" in store.deleted_sessions


# ---- require_sso: local sign-in refused for a verified SSO-only domain (DD-013) ----

_SSO_LOGIN = "/auth/enterprise/login?email=jane%40acme.test"


class _LocalStore(_Store):
    """Adds the local sign-in surface and records every credential-side call."""

    def __init__(self, *, connections=None, superuser: bool = False):
        super().__init__(connections=connections)
        self.local_calls: list[str] = []
        user = _User("uid-jane", "jane@acme.test")
        user.is_active = True
        user.is_superuser = superuser
        user.username = None
        self._users[user.email] = user

    def authenticate(self, email, password):
        self.local_calls.append("authenticate")
        return None

    def get_user_by_email(self, email):
        self.local_calls.append("get_user_by_email")
        return super().get_user_by_email(email)

    def create_password_reset_token(self, user_id):
        self.local_calls.append("create_password_reset_token")
        return "reset-token"

    def _execute_modify(self, sql, params):  # magic_link.create_magic_link's INSERT
        self.local_calls.append("issue_magic_link")
        return 1

    # --- already-issued tokens and a signed-in session (token / change-password paths) ---
    def _execute(self, sql, params=()):  # magic_link.validate_magic_link's SELECT
        self.local_calls.append("magic_link_lookup")
        return [{"user_id": "uid-jane", "expires_at": "2999-01-01T00:00:00+00:00", "used_at": None}]

    def get_user_by_id(self, user_id):
        return self._users["jane@acme.test"]

    def validate_password_reset_token(self, token):
        return self._users["jane@acme.test"]

    def validate_session(self, session_id):
        user = self._users["jane@acme.test"]
        user.password_hash = "not-a-hash"
        return SimpleNamespace(is_authenticated=True, user=user)

    def update_password(self, user_id, new_password):
        self.local_calls.append("update_password")


def _local_client(store: _LocalStore, *, oidc_mounted: bool = True) -> TestClient:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret", same_site="lax")
    app.include_router(create_auth_routes(store))  # type: ignore[arg-type]
    app.include_router(create_password_login_routes())
    app.include_router(create_magic_link_routes())
    app.include_router(create_password_reset_routes())
    app.include_router(create_enterprise_sso_routes())
    app.state.auth_store = store
    if oidc_mounted:
        setattr(app.state, ENTERPRISE_OIDC_STATE_ATTR, True)
    return TestClient(app)


def _sso_conn(**over) -> ConnectionRecord:
    return _conn(config={"require_sso": True}, **over)


def _post(client: TestClient, path: str, kind: str):
    if kind == "json":
        body = {"email": "jane@acme.test", "password": "pw"}
        return client.post(path, json=body, follow_redirects=False)
    form = {"email": "jane@acme.test", "password": "pw", "confirm_password": "pw"}
    return client.post(path, data=form, follow_redirects=False)


# (path, kind): every local sign-in path require_sso refuses.
_REFUSED_PATHS = [
    pytest.param("/auth/login", "json", id="json-login"),
    pytest.param("/auth/forgot-password", "json", id="json-password-reset"),
    pytest.param("/auth/login/password", "form", id="form-login"),
    pytest.param("/auth/login/magic-link", "form", id="magic-link-request"),
    pytest.param("/auth/forgot-password/submit", "form", id="form-password-reset"),
    pytest.param("/auth/register", "json", id="json-register"),
    pytest.param("/auth/signup/password", "form", id="form-signup"),
    pytest.param("/auth/signup/magic-link", "form", id="magic-link-signup"),
]


def _assert_refused(r, kind: str) -> None:
    if kind == "json":
        assert r.status_code == 403
        assert r.json() == {"status": "sso_required", "login_url": _SSO_LOGIN}
    else:
        assert r.status_code == 303
        assert r.headers["location"] == _SSO_LOGIN


@pytest.mark.parametrize(("path", "kind"), _REFUSED_PATHS)
def test_require_sso_refuses_local_sign_in(path: str, kind: str) -> None:
    store = _LocalStore(connections=[_sso_conn()])
    r = _post(_local_client(store), path, kind)
    _assert_refused(r, kind)
    assert store.local_calls == []  # no credential checked, no token or link issued


@pytest.mark.parametrize(("path", "kind"), _REFUSED_PATHS)
def test_require_sso_superuser_not_exempt(path: str, kind: str) -> None:
    store = _LocalStore(connections=[_sso_conn()], superuser=True)
    _assert_refused(_post(_local_client(store), path, kind), kind)


@pytest.mark.parametrize(
    "connection",
    [
        pytest.param(_sso_conn(verified_domains=[]), id="unverified-domain"),
        pytest.param(_conn(config={}), id="flag-off"),
    ],
)
@pytest.mark.parametrize(("path", "kind"), _REFUSED_PATHS)
def test_require_sso_leaves_other_connections_alone(
    path: str, kind: str, connection: ConnectionRecord
) -> None:
    store = _LocalStore(connections=[connection])
    r = _post(_local_client(store), path, kind)
    assert "sso_required" not in r.text
    assert "/auth/enterprise/login" not in r.headers.get("location", "")
    assert store.local_calls  # the local path ran as it does today


_TOKEN = "T" * 43

# (method, path, body, kind): a token minted, or a session opened, before the flag was set.
_ISSUED_CREDENTIAL_REQUESTS = [
    pytest.param("get", f"/auth/magic/{_TOKEN}", None, "form", id="issued-magic-link"),
    pytest.param(
        "post",
        "/auth/reset-password/submit",
        {"token": _TOKEN, "new_password": "n", "confirm_password": "n"},
        "form",
        id="issued-form-reset-token",
    ),
    pytest.param(
        "post",
        "/auth/reset-password",
        {"token": _TOKEN, "new_password": "n"},
        "json",
        id="issued-json-reset-token",
    ),
    pytest.param(
        "post",
        "/auth/change-password",
        {"current_password": "pw", "new_password": "n"},
        "json",
        id="signed-in-change-password",
    ),
]


@pytest.mark.parametrize(("method", "path", "body", "kind"), _ISSUED_CREDENTIAL_REQUESTS)
def test_require_sso_refuses_credentials_issued_before_the_flag(
    method: str, path: str, body: dict | None, kind: str
) -> None:
    store = _LocalStore(connections=[_sso_conn()])
    client = _local_client(store)
    client.cookies.set("dazzle_session", "sid-1")
    if method == "get":
        r = client.get(path, follow_redirects=False)
    elif kind == "json":
        r = client.post(path, json=body, follow_redirects=False)
    else:
        r = client.post(path, data=body, follow_redirects=False)
    _assert_refused(r, kind)
    assert "update_password" not in store.local_calls
    assert store.created_sessions == []


def test_require_sso_form_login_carries_next() -> None:
    store = _LocalStore(connections=[_sso_conn()])
    r = _local_client(store).post(
        "/auth/login/password?next=/app/tasks",
        data={"email": "jane@acme.test", "password": "pw"},
        follow_redirects=False,
    )
    assert r.headers["location"] == f"{_SSO_LOGIN}&next=%2Fapp%2Ftasks"


def test_require_sso_inert_when_oidc_not_mounted() -> None:
    store = _LocalStore(connections=[_sso_conn()])
    r = _post(_local_client(store, oidc_mounted=False), "/auth/login", "json")
    assert r.status_code == 401  # the ordinary bad-credentials answer
    assert store.local_calls == ["authenticate"]


def test_require_sso_redirect_lands_on_the_idp(fake_provider) -> None:
    # The refusal's login_url is the enterprise login, which routes by the verified domain.
    fake_provider(_FakeProvider())
    client = _local_client(_LocalStore(connections=[_sso_conn()]))
    r = client.get(_SSO_LOGIN, follow_redirects=False)
    assert r.status_code == 303
    assert urlparse(r.headers["location"]).hostname == "idp.example"
