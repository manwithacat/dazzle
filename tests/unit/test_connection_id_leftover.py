"""SSO leftover connection id must not invent sso_no_connection (cycle 2240).

leftover-honest urlsafe token already exists (oral #98). Enterprise /
SAML login still forwarded leftover ``?connection=zzz`` / ``ghost``
into get_connection and invented ``303 /login?error=sso_no_connection``.
The same leftover on GET ``/auth/saml/metadata`` invented app-level
metadata. Valid ``secrets.token_urlsafe(24)`` ids ride; leftover stays
put (400, no theater). Absent / blank still first-visit (email-domain /
host-pin / app-level metadata). Well-formed ids that miss the store
still bounce sso_no_connection. Live doctor runbook
``/auth/enterprise/login?connection=``. Oral #110 — not leftover
``?new=`` (oral #97), not leftover consume token (oral #109), not
leftover membership_id (oral #107).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from dazzle.http.runtime.auth.enterprise_routes import create_enterprise_sso_routes
from dazzle.http.runtime.auth.leftover_connection_id import leftover_honest_connection_id
from dazzle.http.runtime.auth.saml_routes import create_saml_routes

_HELPER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "leftover_connection_id.py"
)
_ENTERPRISE = (
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
_STORE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "store.py"
)
_DOCTOR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "connection_doctor.py"
)

# secrets.token_urlsafe(24) is 32 urlsafe chars; token_urlsafe(32) is 43.
_VALID = "A" * 32
_WELLFORMED_MISS = "B" * 32


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (_VALID, _VALID),
        ("b" * 43, "b" * 43),
        ("", ""),
        (None, ""),
        ("   ", ""),
        ("zzz", None),
        ("ghost", None),
        ("conn-1", None),
        ("missing", None),
        ("token:evil", None),
        (f"{_VALID} ", _VALID),
        (["A" * 32], None),
        ({"id": "A" * 32}, None),
        (1, None),
        (True, None),
    ],
    ids=[
        "valid-urlsafe-32",
        "valid-urlsafe-43",
        "empty-default",
        "none-default",
        "blank-default",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-conn-1",
        "leftover-missing",
        "leftover-colon",
        "valid-strip",
        "leftover-list",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
    ],
)
def test_leftover_honest_connection_id_does_not_invent(raw: object, expected: str | None) -> None:
    assert leftover_honest_connection_id(raw) == expected


def _enterprise_app(store: MagicMock) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret", same_site="lax")
    app.state.auth_store = store
    app.include_router(create_enterprise_sso_routes())
    return app


def _saml_app(store: MagicMock) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret", same_site="lax")
    app.state.auth_store = store
    app.include_router(create_saml_routes())
    return app


def test_leftover_enterprise_connection_does_not_invent_sso_no_connection() -> None:
    store = MagicMock()
    client = TestClient(_enterprise_app(store))
    resp = client.get("/auth/enterprise/login?connection=zzz", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown connection" in resp.text
    assert "sso_no_connection" not in (resp.headers.get("location") or "")
    store.get_connection.assert_not_called()


def test_leftover_enterprise_ghost_does_not_invent_sso_no_connection() -> None:
    store = MagicMock()
    client = TestClient(_enterprise_app(store))
    resp = client.get("/auth/enterprise/login?connection=ghost", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown connection" in resp.text
    store.get_connection.assert_not_called()


def test_leftover_saml_connection_does_not_invent_sso_no_connection() -> None:
    store = MagicMock()
    client = TestClient(_saml_app(store))
    resp = client.get("/auth/saml/login?connection=zzz", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown connection" in resp.text
    assert "sso_no_connection" not in (resp.headers.get("location") or "")
    store.get_connection.assert_not_called()


def test_leftover_saml_metadata_does_not_invent_app_level() -> None:
    store = MagicMock()
    client = TestClient(_saml_app(store))
    resp = client.get("/auth/saml/metadata?connection=ghost", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown connection" in resp.text
    store.get_connection.assert_not_called()


def test_absent_enterprise_connection_still_first_visit() -> None:
    store = MagicMock()
    store.get_connection_by_verified_domain.return_value = None
    store.get_connections_for_tenant.return_value = []
    client = TestClient(_enterprise_app(store))
    resp = client.get("/auth/enterprise/login", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=sso_no_connection"
    store.get_connection.assert_not_called()


def test_wellformed_unknown_enterprise_still_sso_no_connection() -> None:
    store = MagicMock()
    store.get_connection.return_value = None
    client = TestClient(_enterprise_app(store))
    resp = client.get(
        f"/auth/enterprise/login?connection={_WELLFORMED_MISS}", follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=sso_no_connection"
    store.get_connection.assert_called_once_with(_WELLFORMED_MISS)


def test_helper_source_pins_connection_id_leftover() -> None:
    helper = _HELPER.read_text()
    enterprise = _ENTERPRISE.read_text()
    saml = _SAML.read_text()
    store = _STORE.read_text()
    doctor = _DOCTOR.read_text()
    assert "def leftover_honest_connection_id" in helper
    assert "def leftover_honest_sso_login_query" in helper
    assert "leftover_honest_auth_token" in helper
    assert "leftover_honest_sso_login_query" in enterprise
    assert "leftover_honest_sso_login_query" in saml
    assert "leftover_honest_connection_id" in saml
    assert "Unknown connection" in helper
    assert "Unknown connection" in saml
    assert "HTMLResponse" in helper
    assert "HTMLResponse" in saml
    assert "token_urlsafe(24)" in store
    assert "/auth/enterprise/login?connection=" in doctor


def test_live_doctor_runbook_names_connection_query() -> None:
    src = _DOCTOR.read_text()
    assert "/auth/enterprise/login?connection=" in src
