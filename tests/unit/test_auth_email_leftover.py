"""Auth leftover email must not invent sent theater / persist / default IdP (cycle 2233).

leftover-honest GET list email VALUE already exists (oral #80). SCIM
userName leftover already exists (oral #102). Magic-link login/signup
still omitted leftover ``email=zzz`` / ``ghost`` as unknown and
invented ``/login/sent``. Forgot-password invented
``/forgot-password/sent``. Invite invented a persist. Enterprise/SAML
``?email=zzz`` invented the host-pinned default IdP. Valid mailboxes
ride; leftover stays put (400, no write / no theater). Absent / blank
still first-visit. Live simple_task ``/auth/login/magic-link``.
Oral #105 — not leftover SCIM userName (oral #102), not leftover GET
list email VALUE (oral #80).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.auth_views import leftover_honest_auth_email
from dazzle.http.runtime.auth.invitation_routes import create_invitation_routes
from dazzle.http.runtime.auth.magic_link_routes import create_magic_link_routes
from dazzle.http.runtime.auth.password_login_routes import create_password_login_routes
from dazzle.http.runtime.auth.password_reset_routes import create_password_reset_routes

_VIEWS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "auth_views.py"
)
_MAGIC = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "magic_link_routes.py"
)
_RESET = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "password_reset_routes.py"
)
_INVITE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "invitation_routes.py"
)
_ENT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "enterprise_routes.py"
)
_SAML = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "saml_routes.py"
)
_PW = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "password_login_routes.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "simple_task" / "dazzle.toml"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ada@acme.test", "ada@acme.test"),
        ("  Ada@Acme.test  ", "ada@acme.test"),
        ("", ""),
        (None, ""),
        ("   ", ""),
        ("zzz", None),
        ("ghost", None),
        ("zzz@ghost", None),
        ("not-an-email", None),
        (["ada@acme.test"], None),
        ({"email": "ada@acme.test"}, None),
        (1, None),
        (True, None),
    ],
    ids=[
        "valid",
        "strip-lower",
        "empty-default",
        "none-default",
        "blank-default",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-no-tld",
        "leftover-prose",
        "leftover-list",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
    ],
)
def test_leftover_honest_auth_email_does_not_invent(raw: object, expected: str | None) -> None:
    assert leftover_honest_auth_email(raw) == expected


def _magic_client() -> TestClient:
    app = FastAPI()
    app.state.auth_store = MagicMock()
    app.include_router(create_magic_link_routes())
    return TestClient(app)


def test_leftover_magic_login_email_does_not_invent_sent() -> None:
    mailer = MagicMock()
    client = _magic_client()
    client.app.state.mailer = mailer
    resp = client.post("/auth/login/magic-link", data={"email": "zzz"}, follow_redirects=False)
    assert resp.status_code == 400
    assert "Invalid email" in resp.text
    mailer.send_magic_link.assert_not_called()


def test_leftover_magic_signup_email_does_not_invent_sent() -> None:
    store = MagicMock()
    app = FastAPI()
    app.state.auth_store = store
    app.include_router(create_magic_link_routes())
    client = TestClient(app)
    client.app.state.mailer = MagicMock()
    resp = client.post(
        "/auth/signup/magic-link",
        data={"email": "ghost", "name": "Ada"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    store.create_user.assert_not_called()


def test_absent_magic_email_still_sent_theater() -> None:
    resp = _magic_client().post(
        "/auth/login/magic-link", data={"email": ""}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login/sent")


def test_valid_magic_email_still_sent() -> None:
    store = MagicMock()
    store.get_user_by_email.return_value = None
    app = FastAPI()
    app.state.auth_store = store
    app.include_router(create_magic_link_routes())
    client = TestClient(app)
    resp = client.post(
        "/auth/login/magic-link",
        data={"email": "ada@acme.test"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login/sent")


def test_leftover_reset_email_does_not_invent_sent() -> None:
    app = FastAPI()
    app.state.auth_store = MagicMock()
    app.include_router(create_password_reset_routes())
    resp = TestClient(app).post(
        "/auth/forgot-password/submit", data={"email": "zzz"}, follow_redirects=False
    )
    assert resp.status_code == 400
    assert "Invalid email" in resp.text


def test_valid_reset_email_still_sent() -> None:
    store = MagicMock()
    store.get_user_by_email.return_value = None
    app = FastAPI()
    app.state.auth_store = store
    app.include_router(create_password_reset_routes())
    resp = TestClient(app).post(
        "/auth/forgot-password/submit",
        data={"email": "ada@acme.test"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/forgot-password/sent"


def _invite_app(store: MagicMock) -> FastAPI:
    app = FastAPI()
    app.state.auth_store = store
    app.state.org_admin_roles = ["admin"]
    app.state.appspec = SimpleNamespace(
        personas=(SimpleNamespace(id="admin"), SimpleNamespace(id="member"))
    )
    app.state.sitespec = {}
    app.include_router(create_invitation_routes())
    return app


def _invite_store() -> MagicMock:
    admin_m = SimpleNamespace(
        id="m-admin",
        tenant_id="org1",
        identity_id="u1",
        roles=["admin"],
        status="active",
    )
    user = SimpleNamespace(id="u1", email="admin@acme.test")
    ctx = SimpleNamespace(is_authenticated=True, user=user, active_membership=admin_m)
    store = MagicMock()
    store.validate_session.return_value = ctx
    return store


def test_leftover_invite_email_does_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[object] = []

    def _create(*_a: object, **_k: object) -> str:
        created.append(_k)
        return "tok"

    monkeypatch.setattr(
        "dazzle.http.runtime.auth.invitations.create_invitation",
        _create,
    )
    store = _invite_store()
    client = TestClient(_invite_app(store), follow_redirects=False)
    client.cookies.set("dazzle_session", "sid")
    resp = client.post("/auth/invite", data={"email": "zzz", "roles": "member"})
    assert resp.status_code == 400
    assert created == []


def test_leftover_password_login_email_does_not_invent_invalid() -> None:
    store = MagicMock()
    app = FastAPI()
    app.state.auth_store = store
    app.include_router(create_password_login_routes())
    resp = TestClient(app).post(
        "/auth/login/password",
        data={"email": "zzz", "password": "secret"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    store.authenticate.assert_not_called()


def test_leftover_password_signup_email_does_not_invent_invalid_banner() -> None:
    store = MagicMock()
    app = FastAPI()
    app.state.auth_store = store
    app.include_router(create_password_login_routes())
    resp = TestClient(app).post(
        "/auth/signup/password",
        data={
            "email": "ghost",
            "name": "Ada",
            "password": "secret12",
            "confirm_password": "secret12",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 400
    store.create_user.assert_not_called()


def test_leftover_enterprise_email_does_not_invent_idp() -> None:
    from dazzle.http.runtime.auth.connections import _PROVIDERS, register_provider
    from tests.integration.test_enterprise_routes import _client, _conn, _FakeProvider, _Store

    register_provider("oidc", "native", _FakeProvider())
    try:
        store = _Store(connections=[_conn()])
        resp = _client(store).get("/auth/enterprise/login?email=zzz", follow_redirects=False)
        assert resp.status_code == 400
        assert "Invalid email" in resp.text
    finally:
        _PROVIDERS.pop(("oidc", "native"), None)


def test_valid_enterprise_email_still_rides() -> None:
    from dazzle.http.runtime.auth.connections import _PROVIDERS, register_provider
    from tests.integration.test_enterprise_routes import _client, _conn, _FakeProvider, _Store

    register_provider("oidc", "native", _FakeProvider())
    try:
        store = _Store(connections=[_conn(verified_domains=["acme.test"])])
        resp = _client(store).get(
            "/auth/enterprise/login?email=jane@acme.test", follow_redirects=False
        )
        assert resp.status_code == 303
        assert "idp.example" in resp.headers["location"]
    finally:
        _PROVIDERS.pop(("oidc", "native"), None)


def test_leftover_saml_email_does_not_invent_idp() -> None:
    from dazzle.http.runtime.auth.connections import _PROVIDERS
    from tests.integration.test_saml_routes import _client, _Store

    resp = _client(_Store(connections=[])).get("/auth/saml/login?email=zzz", follow_redirects=False)
    assert resp.status_code == 400
    assert "Invalid email" in resp.text
    _PROVIDERS.pop(("saml", "native"), None)


def test_helper_source_pins_auth_email_leftover() -> None:
    views = _VIEWS.read_text()
    assert "def leftover_honest_auth_email" in views
    assert "def leftover_auth_email_or_400" in views
    assert 'HTMLResponse("Invalid email", status_code=400)' in views
    magic = _MAGIC.read_text()
    assert "leftover_auth_email_or_400" in magic
    assert "Response(\n                status_code=400,\n                content=" not in magic
    reset = _RESET.read_text()
    assert "leftover_auth_email_or_400" in reset
    invite = _INVITE.read_text()
    assert "leftover_auth_email_or_400" in invite
    ent = _ENT.read_text()
    assert "leftover_auth_email_or_400" in ent
    saml = _SAML.read_text()
    assert "leftover_auth_email_or_400" in saml
    pw = _PW.read_text()
    assert "leftover_auth_email_or_400" in pw


def test_live_simple_task_declares_auth() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
