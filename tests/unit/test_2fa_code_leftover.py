"""2FA leftover codes must not invent invalid_code theater (cycle 2238).

leftover-honest 2FA mode / sent already exist (oral #92 / #94). Verify
POST still posted leftover ``code=zzz`` / ``ghost`` / ``12abc`` into
TOTP / OTP / recovery verify and invented
``303 /2fa/challenge?error=invalid_code``. JSON ``/auth/2fa/verify``
invented ``401 Invalid 2FA code``. Digit codes (6–8) and recovery
``XXXX-XXXX`` ride; leftover stays put (400, no theater). Absent /
blank still first-visit (400 required). Well-formed codes that fail
verify still bounce invalid_code. Live simple_task ``/2fa/challenge``.
Oral #108 — not leftover 2FA mode (oral #92), not leftover 2FA sent
(oral #94).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.leftover_2fa_code import leftover_honest_2fa_code
from dazzle.http.runtime.auth.two_factor_form_routes import create_two_factor_form_routes

_HELPER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "leftover_2fa_code.py"
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
_JSON = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "routes_2fa.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "simple_task" / "dazzle.toml"

_SID = "A" * 43


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("123456", "123456"),
        ("000000", "000000"),
        ("12345678", "12345678"),
        ("123 456", "123456"),
        ("A2B3-C4D5", "A2B3-C4D5"),
        ("a2b3c4d5", "A2B3-C4D5"),
        ("", ""),
        (None, ""),
        ("   ", ""),
        ("zzz", None),
        ("ghost", None),
        ("12abc", None),
        ("12345", None),
        ("not-a-code", None),
        (["123456"], None),
        ({"code": "123456"}, None),
        (1, None),
        (True, None),
    ],
    ids=[
        "totp-6",
        "totp-zeros",
        "otp-8",
        "totp-spaced",
        "recovery-dashed",
        "recovery-compact",
        "empty-default",
        "none-default",
        "blank-default",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-mixed",
        "leftover-short-digits",
        "leftover-dashed-words",
        "leftover-list",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
    ],
)
def test_leftover_honest_2fa_code_does_not_invent(raw: object, expected: str | None) -> None:
    assert leftover_honest_2fa_code(raw) == expected


def _form_app(store: MagicMock | SimpleNamespace) -> FastAPI:
    app = FastAPI()
    app.state.auth_store = store
    app.include_router(create_two_factor_form_routes())
    return app


def test_leftover_verify_code_does_not_invent_invalid_code() -> None:
    store = MagicMock()
    client = TestClient(_form_app(store))
    resp = client.post(
        "/auth/2fa/verify/submit",
        data={"session_token": _SID, "method": "totp", "code": "zzz"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Unknown 2FA code" in resp.text
    assert "invalid_code" not in (resp.headers.get("location") or "")
    store.validate_session.assert_not_called()


def test_leftover_verify_ghost_code_does_not_invent_invalid_code() -> None:
    store = MagicMock()
    client = TestClient(_form_app(store))
    resp = client.post(
        "/auth/2fa/verify/submit",
        data={"session_token": _SID, "method": "totp", "code": "ghost"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Unknown 2FA code" in resp.text
    store.validate_session.assert_not_called()


def test_absent_code_still_first_visit() -> None:
    store = MagicMock()
    client = TestClient(_form_app(store))
    resp = client.post(
        "/auth/2fa/verify/submit",
        data={"session_token": _SID, "method": "totp", "code": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Code required" in resp.text
    assert "invalid_code" not in (resp.headers.get("location") or "")
    store.validate_session.assert_not_called()


def test_wellformed_wrong_code_still_invalid_code() -> None:
    user = SimpleNamespace(id="u1")
    ctx = SimpleNamespace(is_authenticated=True, user=user)
    store = MagicMock()
    store.validate_session.return_value = ctx
    store.get_totp_secret.return_value = "JBSWY3DPEHPK3PXP"
    client = TestClient(_form_app(store))
    resp = client.post(
        "/auth/2fa/verify/submit",
        data={"session_token": _SID, "method": "totp", "code": "000000"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "error=invalid_code" in (resp.headers.get("location") or "")
    store.validate_session.assert_called_once()


def test_helper_source_pins_2fa_code_leftover() -> None:
    helper = _HELPER.read_text()
    assert "def leftover_honest_2fa_code" in helper
    assert "_2FA_RECOVERY_ALPHABET" in helper
    form = _FORM.read_text()
    assert "leftover_honest_2fa_code" in form
    assert "Unknown 2FA code" in form
    assert "Code required" in form
    assert "HTMLResponse" in form
    assert "Response(\n                status_code=400,\n                content=" not in form
    json_routes = _JSON.read_text()
    assert "leftover_honest_2fa_code" in json_routes
    assert "def _require_2fa_code" in json_routes
    assert "Unknown 2FA code" in json_routes


def test_live_simple_task_declares_auth_login() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
