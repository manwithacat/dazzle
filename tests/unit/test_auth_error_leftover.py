"""Auth leftover ?error= tokens must not invent a clean page (cycle 2221).

leftover-honest 2FA sent/mode already exist (oral #94 / #92). Login
still omitted leftover ``?error=zzz`` as absent and invented a clean
sign-in. Enterprise/SAML already emit ``sso_no_connection`` /
``sso_unavailable`` / ``sso_{reason}`` — those vanished the same way.
Valid declared tokens ride; leftover stays put (400, no invented
clean page). Live simple_task ``/login``. Oral #95 — not leftover
2FA sent (oral #94), not leftover 2FA mode (oral #92).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.auth_views import (
    LOGIN_ERROR_MESSAGES,
    leftover_honest_auth_error,
)
from dazzle.http.runtime.auth.org_context_routes import create_org_context_routes
from dazzle.http.runtime.site_routes import create_auth_page_routes

_VIEWS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "auth_views.py"
)
_SITE = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "site_routes.py"
)
_ORG = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "org_context_routes.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "simple_task" / "dazzle.toml"


@pytest.mark.parametrize(
    ("raw", "declared", "expected"),
    [
        ("invalid_credentials", ("invalid_credentials", "sso_failed"), "invalid_credentials"),
        ("sso_no_connection", ("sso_no_connection", "sso_failed"), "sso_no_connection"),
        ("", ("invalid_credentials",), ""),
        (None, ("invalid_credentials",), ""),
        ("   ", ("invalid_credentials",), ""),
        ("zzz", ("invalid_credentials",), None),
        ("ghost", ("invalid_credentials",), None),
        ("sso_failed ", ("sso_failed",), "sso_failed"),
        ("INVALID_CREDENTIALS", ("invalid_credentials",), None),
    ],
    ids=[
        "valid-credentials",
        "valid-sso-no-connection",
        "empty-default",
        "none-default",
        "blank-default",
        "leftover-zzz",
        "leftover-ghost",
        "valid-strip",
        "leftover-case",
    ],
)
def test_leftover_honest_auth_error_does_not_invent(
    raw: object, declared: tuple[str, ...], expected: str | None
) -> None:
    assert leftover_honest_auth_error(raw, declared) == expected


def _site_client() -> TestClient:
    app = FastAPI()
    app.include_router(create_auth_page_routes({"brand": {"product_name": "Acme"}}))
    return TestClient(app)


def test_leftover_login_error_does_not_invent_clean_page() -> None:
    resp = _site_client().get("/login?error=zzz")
    assert resp.status_code == 400
    assert "Unknown login error" in resp.text
    assert "Sign in" not in resp.text or "Unknown login error" in resp.text
    assert "didn't match" not in resp.text


def test_leftover_login_error_ghost_does_not_invent_banner() -> None:
    resp = _site_client().get("/login?error=ghost")
    assert resp.status_code == 400
    assert "We couldn't complete the sign-in" not in resp.text


def test_absent_login_error_still_renders_form() -> None:
    resp = _site_client().get("/login")
    assert resp.status_code == 200
    assert "Send sign-in link" in resp.text or "Sign in" in resp.text
    assert "Unknown login error" not in resp.text


def test_valid_login_error_still_renders_banner() -> None:
    resp = _site_client().get("/login?error=invalid_credentials")
    assert resp.status_code == 200
    assert "That email and password didn't match. Try again." in resp.text


def test_declared_sso_no_connection_rides() -> None:
    resp = _site_client().get("/login?error=sso_no_connection")
    assert resp.status_code == 200
    assert LOGIN_ERROR_MESSAGES["sso_no_connection"] in resp.text


def test_declared_sso_unavailable_rides() -> None:
    resp = _site_client().get("/login?error=sso_unavailable")
    assert resp.status_code == 200
    assert LOGIN_ERROR_MESSAGES["sso_unavailable"] in resp.text


def test_declared_sso_domain_not_verified_rides() -> None:
    resp = _site_client().get("/login?error=sso_domain_not_verified")
    assert resp.status_code == 200
    assert LOGIN_ERROR_MESSAGES["sso_domain_not_verified"] in resp.text


def test_leftover_signup_error_stays_put() -> None:
    resp = _site_client().get("/signup?error=zzz")
    assert resp.status_code == 400
    assert "Unknown signup error" in resp.text


def test_valid_signup_error_rides() -> None:
    resp = _site_client().get("/signup?error=already_registered")
    assert resp.status_code == 200
    assert "already exists" in resp.text


def test_leftover_reset_error_stays_put() -> None:
    resp = _site_client().get("/reset-password?error=zzz")
    assert resp.status_code == 400
    assert "Unknown reset error" in resp.text


def test_valid_reset_error_rides() -> None:
    resp = _site_client().get("/reset-password?error=invalid")
    assert resp.status_code == 200
    assert "invalid or expired" in resp.text


def test_leftover_2fa_error_stays_put() -> None:
    resp = _site_client().get("/2fa/challenge?session=sid&mode=totp&error=zzz")
    assert resp.status_code == 400
    assert "Unknown 2FA error" in resp.text


def test_valid_2fa_error_rides() -> None:
    resp = _site_client().get("/2fa/challenge?session=sid&mode=totp&error=invalid_code")
    assert resp.status_code == 200
    assert "That code didn't match. Try again." in resp.text


def _org_client() -> TestClient:
    app = FastAPI()

    class _Store:
        def validate_session(self, _sid: object) -> object:
            return type("Ctx", (), {"is_authenticated": False, "user": None})()

    app.state.auth_store = _Store()
    app.include_router(create_org_context_routes())
    return TestClient(app)


def test_leftover_select_org_error_stays_put() -> None:
    resp = _org_client().get("/auth/select-org?error=zzz")
    assert resp.status_code == 400
    assert "Unknown org error" in resp.text


def test_valid_select_org_error_rides() -> None:
    resp = _org_client().get("/auth/select-org?error=invalid_org")
    assert resp.status_code == 200
    assert "That organization isn't available" in resp.text


def test_helper_source_pins_auth_error_leftover() -> None:
    views = _VIEWS.read_text()
    assert "def leftover_honest_auth_error" in views
    assert "leftover_honest_catalog_id" in views
    assert "sso_no_connection" in views
    site = _SITE.read_text()
    assert "leftover_honest_auth_error" in site
    assert "Unknown login error" in site
    assert "HTMLResponse" in site
    assert 'error == "sso_failed"' not in site
    org = _ORG.read_text()
    assert "leftover_honest_auth_error" in org
    assert "Unknown org error" in org


def test_live_simple_task_declares_auth_login() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
