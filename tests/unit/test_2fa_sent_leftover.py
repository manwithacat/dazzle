"""2FA leftover sent tokens must not invent code-sent theater (cycle 2218).

leftover-honest 2FA mode already exists (oral #92). Challenge GET still
coerced leftover ``?sent=zzz`` / ``false`` / ``0`` to ``code_sent=True``
via ``bool(sent)`` and rendered "Code sent — check your email." while
hiding the send-code button. Valid ``sent=1`` rides; leftover stays put
(400, no invented theater). Live simple_task auth ``/2fa/challenge``.
Oral #94 — not leftover 2FA mode (oral #92), not leftover consent bool
(oral #90).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.two_factor_views import leftover_honest_2fa_sent
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
        ("1", True),
        ("", False),
        (None, False),
        ("   ", False),
        ("zzz", None),
        ("ghost", None),
        ("0", None),
        ("false", None),
        ("true", None),
        ("yes", None),
        ("1 ", True),
    ],
    ids=[
        "sent-one",
        "empty-default",
        "none-default",
        "blank-default",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-zero",
        "leftover-false",
        "leftover-true",
        "leftover-yes",
        "valid-strip",
    ],
)
def test_leftover_honest_2fa_sent_does_not_invent(raw: object, expected: bool | None) -> None:
    assert leftover_honest_2fa_sent(raw) == expected


def _challenge_client() -> TestClient:
    app = FastAPI()
    app.include_router(create_auth_page_routes({"brand": {"product_name": "Acme"}}))
    return TestClient(app)


def test_leftover_sent_does_not_invent_code_sent_theater() -> None:
    resp = _challenge_client().get("/2fa/challenge?session=sid&mode=email_otp&sent=zzz")
    assert resp.status_code == 400
    assert "Unknown 2FA sent flag" in resp.text
    assert "Code sent — check your email." not in resp.text
    assert "Send code to email" not in resp.text


def test_leftover_sent_false_does_not_invent_code_sent() -> None:
    resp = _challenge_client().get("/2fa/challenge?session=sid&mode=email_otp&sent=false")
    assert resp.status_code == 400
    assert "Code sent — check your email." not in resp.text


def test_absent_sent_still_shows_send_code() -> None:
    resp = _challenge_client().get("/2fa/challenge?session=sid&mode=email_otp")
    assert resp.status_code == 200
    assert "Send code to email" in resp.text
    assert "Code sent — check your email." not in resp.text


def test_valid_sent_one_still_renders_code_sent() -> None:
    resp = _challenge_client().get("/2fa/challenge?session=sid&mode=email_otp&sent=1")
    assert resp.status_code == 200
    assert "Code sent — check your email." in resp.text
    assert "Send code to email" not in resp.text


def test_helper_source_pins_2fa_sent_leftover() -> None:
    views = _VIEWS.read_text()
    assert "def leftover_honest_2fa_sent" in views
    assert "leftover_honest_catalog_id" in views
    site = _SITE.read_text()
    assert "leftover_honest_2fa_sent" in site
    assert "Unknown 2FA sent flag" in site
    assert "code_sent=bool(sent)" not in site
    assert "HTMLResponse" in site
    form = _FORM.read_text()
    assert "sent=1" in form


def test_live_simple_task_declares_auth_login() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
