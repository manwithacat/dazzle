"""Connections leftover ?new= must not invent a clean list (cycle 2223).

leftover-honest catalog picker already exists (oral #69). Connections
GET still omitted leftover ``?new=zzz`` / ``ghost`` as absent and
invented the default connections page (chooser links, no create form).
Valid ``oidc`` / ``scim`` / ``saml`` / ``domain`` ride; leftover stays
put (400, no invented clean list). Live simple_task
``/auth/connections``. Oral #97 — not leftover catalog picker
(oral #69), not leftover 2FA sent (oral #94), not leftover auth next
(oral #96).
"""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.connection_admin_routes import create_connection_admin_routes
from dazzle.http.runtime.auth.connection_admin_views import leftover_honest_connection_new

_VIEWS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "connection_admin_views.py"
)
_ROUTES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "connection_admin_routes.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "simple_task" / "dazzle.toml"


@pytest.fixture(autouse=True)
def _connection_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(b"k" * 32).decode())


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("oidc", "oidc"),
        ("scim", "scim"),
        ("saml", "saml"),
        ("domain", "domain"),
        ("", ""),
        (None, ""),
        ("   ", ""),
        ("zzz", None),
        ("ghost", None),
        ("totp", None),
        ("OIDC", None),
        ("oidc ", "oidc"),
    ],
    ids=[
        "valid-oidc",
        "valid-scim",
        "valid-saml",
        "valid-domain",
        "empty-default",
        "none-default",
        "blank-default",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-totp",
        "leftover-case",
        "valid-strip",
    ],
)
def test_leftover_honest_connection_new_does_not_invent(raw: object, expected: str | None) -> None:
    assert leftover_honest_connection_new(raw) == expected


class _Store:
    def validate_session(self, session_id: object) -> object:
        if session_id != "good-sid":
            return None
        return SimpleNamespace(
            is_authenticated=True,
            user=SimpleNamespace(id="u1"),
            active_membership=SimpleNamespace(tenant_id="org-1", roles=("admin",), status="active"),
        )

    def get_connections_for_tenant(self, tenant_id: object) -> list[object]:
        return []

    def get_org_settings(self, org_id: object) -> dict[str, object]:
        return {}

    def get_organization(self, org_id: object) -> object:
        return SimpleNamespace(name="Acme Inc")


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(create_connection_admin_routes())
    app.state.auth_store = _Store()
    app.state.org_admin_roles = ["admin"]
    app.state.sitespec = {"brand": {"product_name": "Acme"}}
    client = TestClient(app)
    client.cookies.set("dazzle_session", "good-sid")
    return client


def test_leftover_new_does_not_invent_clean_list() -> None:
    resp = _client().get("/auth/connections?new=zzz")
    assert resp.status_code == 400
    assert "Unknown connection type" in resp.text
    assert "Create OIDC connection" not in resp.text
    assert "Add OIDC" not in resp.text


def test_leftover_new_ghost_does_not_invent_chooser() -> None:
    resp = _client().get("/auth/connections?new=ghost")
    assert resp.status_code == 400
    assert "Unknown connection type" in resp.text
    assert "Add a connection" not in resp.text


def test_absent_new_still_renders_chooser() -> None:
    resp = _client().get("/auth/connections")
    assert resp.status_code == 200
    assert "Add a connection" in resp.text
    assert "Add OIDC" in resp.text
    assert "Create OIDC connection" not in resp.text
    assert "Unknown connection type" not in resp.text


def test_valid_new_oidc_rides() -> None:
    resp = _client().get("/auth/connections?new=oidc")
    assert resp.status_code == 200
    assert "Create OIDC connection" in resp.text
    assert "Unknown connection type" not in resp.text


def test_valid_new_domain_rides() -> None:
    resp = _client().get("/auth/connections?new=domain")
    assert resp.status_code == 200
    assert "Verify a domain (no SSO)" in resp.text
    assert "Unknown connection type" not in resp.text


def test_helper_source_pins_connection_new_leftover() -> None:
    views = _VIEWS.read_text()
    assert "def leftover_honest_connection_new" in views
    assert "leftover_honest_auth_error" in views
    routes = _ROUTES.read_text()
    assert "leftover_honest_connection_new" in routes
    assert "Unknown connection type" in routes
    assert "HTMLResponse" in routes


def test_live_simple_task_declares_auth() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
