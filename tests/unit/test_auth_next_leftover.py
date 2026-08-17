"""Auth leftover ?next= must not invent the default landing (cycle 2222).

leftover-honest auth error already exists (oral #95). Login still
omitted leftover ``?next=zzz`` / ``https://evil.com`` as absent and
invented the default landing (form omit, then ``/app`` after login).
Valid same-origin paths ride; leftover stays put (400, no invented
clean form / landing). Live simple_task ``/login``. Oral #96 — not
leftover auth error (oral #95), not leftover 2FA sent (oral #94).
POST leftover next stays fail-closed to ``/app`` (security).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.org_context_routes import create_org_context_routes
from dazzle.http.runtime.auth.redirect_safety import leftover_honest_auth_next
from dazzle.http.runtime.site_routes import create_auth_page_routes

_SAFETY = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "redirect_safety.py"
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
    ("raw", "expected"),
    [
        ("/app", "/app"),
        ("/workspaces/my_work", "/workspaces/my_work"),
        ("/2fa/setup", "/2fa/setup"),
        ("", ""),
        (None, ""),
        ("   ", ""),
        ("/", ""),
        ("zzz", None),
        ("ghost", None),
        ("https://evil.com", None),
        ("//evil.com", None),
        ("javascript:alert(1)", None),
        ("/app ", "/app"),
    ],
    ids=[
        "valid-app",
        "valid-workspace",
        "valid-2fa-setup",
        "empty-default",
        "none-default",
        "blank-default",
        "slash-default",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-absolute",
        "leftover-protocol-relative",
        "leftover-javascript",
        "valid-strip",
    ],
)
def test_leftover_honest_auth_next_does_not_invent(raw: object, expected: str | None) -> None:
    assert leftover_honest_auth_next(raw) == expected


def _site_client() -> TestClient:
    app = FastAPI()
    app.include_router(create_auth_page_routes({"brand": {"product_name": "Acme"}}))
    return TestClient(app)


def test_leftover_login_next_does_not_invent_clean_form() -> None:
    resp = _site_client().get("/login?next=zzz")
    assert resp.status_code == 400
    assert "Unknown login next" in resp.text
    assert "Send sign-in link" not in resp.text


def test_leftover_login_next_absolute_does_not_invent_landing() -> None:
    resp = _site_client().get("/login?next=https://evil.com")
    assert resp.status_code == 400
    assert "Unknown login next" in resp.text
    assert "magic-link?next=https://evil.com" not in resp.text


def test_absent_login_next_still_renders_form() -> None:
    resp = _site_client().get("/login")
    assert resp.status_code == 200
    assert "Send sign-in link" in resp.text or "Sign in" in resp.text
    assert "Unknown login next" not in resp.text


def test_valid_login_next_rides() -> None:
    resp = _site_client().get("/login?next=/app")
    assert resp.status_code == 200
    assert "Send sign-in link" in resp.text or "Sign in" in resp.text
    assert "Unknown login next" not in resp.text
    assert "next=/app" in resp.text


def test_leftover_signup_next_stays_put() -> None:
    resp = _site_client().get("/signup?next=zzz")
    assert resp.status_code == 400
    assert "Unknown signup next" in resp.text


def test_valid_signup_next_rides() -> None:
    resp = _site_client().get("/signup?next=/app")
    assert resp.status_code == 200
    assert "Unknown signup next" not in resp.text


def _org_client() -> TestClient:
    app = FastAPI()

    class _Store:
        def validate_session(self, _sid: object) -> object:
            return type("Ctx", (), {"is_authenticated": False, "user": None})()

    app.state.auth_store = _Store()
    app.include_router(create_org_context_routes())
    return TestClient(app)


def test_leftover_select_org_next_stays_put() -> None:
    resp = _org_client().get("/auth/select-org?next=zzz")
    assert resp.status_code == 400
    assert "Unknown org next" in resp.text


def test_valid_select_org_next_rides() -> None:
    resp = _org_client().get("/auth/select-org?next=/app")
    assert resp.status_code == 200
    assert "Unknown org next" not in resp.text


def test_absent_select_org_next_still_renders() -> None:
    resp = _org_client().get("/auth/select-org")
    assert resp.status_code == 200
    assert "Unknown org next" not in resp.text


def test_helper_source_pins_auth_next_leftover() -> None:
    safety = _SAFETY.read_text()
    assert "def leftover_honest_auth_next" in safety
    assert "is_safe_redirect_path" in safety
    site = _SITE.read_text()
    assert "leftover_honest_auth_next" in site
    assert "Unknown login next" in site
    assert "Unknown signup next" in site
    assert "HTMLResponse" in site
    org = _ORG.read_text()
    assert "leftover_honest_auth_next" in org
    assert "Unknown org next" in org


def test_live_simple_task_declares_auth_login() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
