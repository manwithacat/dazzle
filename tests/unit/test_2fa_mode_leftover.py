"""2FA leftover mode tokens must not invent totp (cycle 2215).

leftover-honest catalog id already exists (oral #69). Challenge GET
still coerced leftover ``?mode=zzz`` / ``?method=zzz`` to ``totp``
and rendered the authenticator form. Valid declared modes ride;
leftover stays put (400, no invented totp). Live simple_task auth
``/2fa/challenge``. Oral #92 — not leftover join-policy (oral #91),
not leftover catalog picker (oral #69).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.two_factor_form_routes import create_two_factor_form_routes
from dazzle.http.runtime.auth.two_factor_views import leftover_honest_2fa_mode
from dazzle.http.runtime.site_routes import create_auth_page_routes

_VIEWS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "two_factor_views.py"
)
_SITE = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "site_routes.py"
)
_FORM = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "two_factor_form_routes.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "simple_task" / "dazzle.toml"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("totp", "totp"),
        ("email_otp", "email_otp"),
        ("recovery", "recovery"),
        ("", "totp"),
        (None, "totp"),
        ("   ", "totp"),
        ("zzz", None),
        ("ghost", None),
        ("TOTP", None),
        ("sms", None),
        ("totp ", "totp"),
    ],
    ids=[
        "totp",
        "email-otp",
        "recovery",
        "empty-default",
        "none-default",
        "blank-default",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-case",
        "leftover-sms",
        "valid-strip",
    ],
)
def test_leftover_honest_2fa_mode_does_not_invent(raw: object, expected: str | None) -> None:
    assert leftover_honest_2fa_mode(raw) == expected


def _challenge_client() -> TestClient:
    app = FastAPI()
    app.include_router(create_auth_page_routes({"brand": {"product_name": "Acme"}}))
    return TestClient(app)


def test_leftover_mode_does_not_invent_totp_page() -> None:
    resp = _challenge_client().get("/2fa/challenge?session=sid&mode=zzz")
    assert resp.status_code == 400
    assert "Unknown 2FA method" in resp.text
    assert "Authenticator code" not in resp.text


def test_leftover_legacy_method_does_not_invent_totp_page() -> None:
    resp = _challenge_client().get("/2fa/challenge?session=sid&method=ghost")
    assert resp.status_code == 400
    assert "Authenticator code" not in resp.text


def test_absent_mode_still_defaults_totp() -> None:
    resp = _challenge_client().get("/2fa/challenge?session=sid")
    assert resp.status_code == 200
    assert "Authenticator code" in resp.text


def test_valid_mode_still_renders() -> None:
    resp = _challenge_client().get("/2fa/challenge?session=sid&mode=email_otp")
    assert resp.status_code == 200
    assert "Enter the code we sent to your email." in resp.text


def test_leftover_verify_method_stays_put() -> None:
    app = FastAPI()
    app.state.auth_store = SimpleNamespace()
    app.include_router(create_two_factor_form_routes())
    resp = TestClient(app).post(
        "/auth/2fa/verify/submit",
        data={"session_token": "sid", "method": "zzz", "code": "123456"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Unknown 2FA method" in resp.text


def test_helper_source_pins_2fa_mode_leftover() -> None:
    views = _VIEWS.read_text()
    assert "def leftover_honest_2fa_mode" in views
    assert "leftover_honest_catalog_id" in views
    site = _SITE.read_text()
    assert "leftover_honest_2fa_mode" in site
    assert "Unknown 2FA method" in site
    form = _FORM.read_text()
    assert "leftover_honest_2fa_mode" in form
    assert "Unknown 2FA method" in form


def test_live_simple_task_declares_auth_login() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
