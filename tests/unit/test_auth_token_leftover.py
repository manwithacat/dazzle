"""Auth leftover urlsafe tokens must not invent a reset / 2FA form (cycle 2224).

leftover-honest auth error already exists (oral #95). Reset GET still
echoed leftover ``?token=zzz`` / ``ghost`` into the reset form and
invented token theater. 2FA GET echoed leftover ``?session=zzz`` the
same way. Valid ``secrets.token_urlsafe(32)`` tokens ride; leftover
stays put (400, no invented form). Live simple_task ``/reset-password``
+ ``/2fa/challenge``. Oral #98 — not leftover auth error (oral #95),
not leftover 2FA mode (oral #92), not leftover 2FA sent (oral #94).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.auth_views import leftover_honest_auth_token
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
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "simple_task" / "dazzle.toml"

# secrets.token_urlsafe(32) is 43 urlsafe chars.
_VALID = "A" * 43


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (_VALID, _VALID),
        ("b" * 32, "b" * 32),
        ("", ""),
        (None, ""),
        ("   ", ""),
        ("zzz", None),
        ("ghost", None),
        ("sid", None),
        ("token:evil", None),
        ("https://evil.com", None),
        (f"{_VALID} ", _VALID),
    ],
    ids=[
        "valid-urlsafe-43",
        "valid-min-32",
        "empty-default",
        "none-default",
        "blank-default",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-sid",
        "leftover-colon",
        "leftover-url",
        "valid-strip",
    ],
)
def test_leftover_honest_auth_token_does_not_invent(raw: object, expected: str | None) -> None:
    assert leftover_honest_auth_token(raw) == expected


def _site_client() -> TestClient:
    app = FastAPI()
    app.include_router(create_auth_page_routes({"brand": {"product_name": "Acme"}}))
    return TestClient(app)


def test_leftover_reset_token_does_not_invent_form() -> None:
    resp = _site_client().get("/reset-password?token=zzz")
    assert resp.status_code == 400
    assert "Unknown reset token" in resp.text
    assert "Save new password" not in resp.text
    assert "Set a new password" not in resp.text


def test_leftover_reset_token_ghost_does_not_invent_form() -> None:
    resp = _site_client().get("/reset-password?token=ghost")
    assert resp.status_code == 400
    assert "Unknown reset token" in resp.text
    assert "Save new password" not in resp.text


def test_absent_reset_token_still_renders_form() -> None:
    resp = _site_client().get("/reset-password")
    assert resp.status_code == 200
    assert "Save new password" in resp.text
    assert "Unknown reset token" not in resp.text


def test_valid_reset_token_rides() -> None:
    resp = _site_client().get(f"/reset-password?token={_VALID}")
    assert resp.status_code == 200
    assert "Save new password" in resp.text
    assert _VALID in resp.text
    assert "Unknown reset token" not in resp.text


def test_leftover_2fa_session_does_not_invent_form() -> None:
    resp = _site_client().get("/2fa/challenge?session=zzz")
    assert resp.status_code == 400
    assert "Unknown 2FA session" in resp.text
    assert "Authenticator code" not in resp.text
    assert "Verify your identity" not in resp.text


def test_leftover_2fa_session_sid_does_not_invent_form() -> None:
    resp = _site_client().get("/2fa/challenge?session=sid&mode=totp")
    assert resp.status_code == 400
    assert "Unknown 2FA session" in resp.text
    assert "Authenticator code" not in resp.text


def test_absent_2fa_session_still_renders_form() -> None:
    resp = _site_client().get("/2fa/challenge")
    assert resp.status_code == 200
    assert "Authenticator code" in resp.text
    assert "Unknown 2FA session" not in resp.text


def test_valid_2fa_session_rides() -> None:
    resp = _site_client().get(f"/2fa/challenge?session={_VALID}&mode=totp")
    assert resp.status_code == 200
    assert "Authenticator code" in resp.text
    assert _VALID in resp.text
    assert "Unknown 2FA session" not in resp.text


def test_helper_source_pins_auth_token_leftover() -> None:
    views = _VIEWS.read_text()
    assert "def leftover_honest_auth_token" in views
    assert "_AUTH_URLSAFE_TOKEN" in views
    site = _SITE.read_text()
    assert "leftover_honest_auth_token" in site
    assert "Unknown reset token" in site
    assert "Unknown 2FA session" in site
    assert "HTMLResponse" in site


def test_live_simple_task_declares_auth() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
