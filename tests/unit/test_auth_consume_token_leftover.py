"""Auth leftover consume tokens must not invent invalid theater (cycle 2239).

leftover-honest urlsafe echo already exists (oral #98). Consume still
posted leftover ``/auth/magic/zzz`` / ``ghost`` into validate and
invented ``303 /auth/login?error=invalid_magic_link``. The same leftover
on POST ``/auth/reset-password/submit`` invented ``?error=invalid``;
on GET ``/auth/verify-email?token=zzz`` invented ``verified=error``;
on GET/POST accept-invite invented the invalid-or-used page. Valid
``secrets.token_urlsafe(32)`` tokens ride; leftover stays put (400, no
theater). Absent / blank still first-visit. Well-formed tokens that
fail validate still bounce invalid. Live simple_task ``/auth/magic``.
Oral #109 — not leftover auth token echo (oral #98).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.auth_views import leftover_honest_auth_token
from dazzle.http.runtime.auth.email_verification_routes import create_email_verification_routes
from dazzle.http.runtime.auth.invitation_routes import create_invitation_routes
from dazzle.http.runtime.auth.magic_link_routes import create_magic_link_routes
from dazzle.http.runtime.auth.password_reset_routes import create_password_reset_routes

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
_VERIFY = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "email_verification_routes.py"
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
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "simple_task" / "dazzle.toml"

_VALID = "A" * 43
_WELLFORMED_MISS = "B" * 43


def test_leftover_honest_auth_token_still_rejects_zzz() -> None:
    assert leftover_honest_auth_token("zzz") is None
    assert leftover_honest_auth_token("ghost") is None
    assert leftover_honest_auth_token(_VALID) == _VALID


def _magic_app(store: MagicMock) -> FastAPI:
    app = FastAPI()
    app.state.auth_store = store
    app.include_router(create_magic_link_routes())
    return app


def test_leftover_magic_token_does_not_invent_invalid_magic_link() -> None:
    store = MagicMock()
    client = TestClient(_magic_app(store))
    resp = client.get("/auth/magic/zzz", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown magic link" in resp.text
    assert "invalid_magic_link" not in (resp.headers.get("location") or "")
    store.get_user_by_id.assert_not_called()


def test_leftover_magic_ghost_does_not_invent_invalid_magic_link() -> None:
    store = MagicMock()
    client = TestClient(_magic_app(store))
    resp = client.get("/auth/magic/ghost", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown magic link" in resp.text


def test_wellformed_unknown_magic_still_invalid_magic_link() -> None:
    store = MagicMock()
    client = TestClient(_magic_app(store))
    with patch(
        "dazzle.http.runtime.auth.magic_link_routes.validate_magic_link",
        return_value=None,
    ):
        resp = client.get(f"/auth/magic/{_WELLFORMED_MISS}", follow_redirects=False)
    assert resp.status_code == 303
    assert "error=invalid_magic_link" in (resp.headers.get("location") or "")


def test_valid_magic_token_still_creates_session() -> None:
    user = MagicMock()
    user.id = "user-123"
    session = MagicMock()
    session.id = "session-token-abc"
    session.csrf_secret = "csrf"
    store = MagicMock()
    store.get_user_by_id.return_value = user
    store.create_session.return_value = session
    store.get_memberships_for_identity.return_value = []
    client = TestClient(_magic_app(store))
    with patch(
        "dazzle.http.runtime.auth.magic_link_routes.validate_magic_link",
        return_value="user-123",
    ):
        resp = client.get(f"/auth/magic/{_VALID}", follow_redirects=False)
    assert resp.status_code == 303


def _reset_app(store: MagicMock) -> FastAPI:
    app = FastAPI()
    app.state.auth_store = store
    app.include_router(create_password_reset_routes())
    return app


def test_leftover_reset_token_does_not_invent_invalid() -> None:
    store = MagicMock()
    client = TestClient(_reset_app(store))
    resp = client.post(
        "/auth/reset-password/submit",
        data={"token": "zzz", "new_password": "newpass123", "confirm_password": "newpass123"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Unknown reset token" in resp.text
    assert "error=invalid" not in (resp.headers.get("location") or "")
    store.validate_password_reset_token.assert_not_called()


def test_leftover_reset_token_mismatch_does_not_echo_junk() -> None:
    store = MagicMock()
    client = TestClient(_reset_app(store))
    resp = client.post(
        "/auth/reset-password/submit",
        data={"token": "ghost", "new_password": "a", "confirm_password": "b"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Unknown reset token" in resp.text
    loc = resp.headers.get("location") or ""
    assert "ghost" not in loc
    assert "error=mismatch" not in loc


def test_absent_reset_token_still_first_visit() -> None:
    store = MagicMock()
    client = TestClient(_reset_app(store))
    resp = client.post(
        "/auth/reset-password/submit",
        data={"token": "", "new_password": "newpass123", "confirm_password": "newpass123"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Reset token required" in resp.text
    store.validate_password_reset_token.assert_not_called()


def test_wellformed_unknown_reset_still_invalid() -> None:
    store = MagicMock()
    store.validate_password_reset_token.return_value = None
    client = TestClient(_reset_app(store))
    resp = client.post(
        "/auth/reset-password/submit",
        data={
            "token": _WELLFORMED_MISS,
            "new_password": "newpass123",
            "confirm_password": "newpass123",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/reset-password?error=invalid"


def _verify_app(store: MagicMock) -> FastAPI:
    app = FastAPI()
    app.state.auth_store = store
    app.include_router(create_email_verification_routes())
    return app


def test_leftover_verify_token_does_not_invent_verified_error() -> None:
    store = MagicMock()
    client = TestClient(_verify_app(store))
    resp = client.get("/auth/verify-email?token=zzz", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown verification token" in resp.text
    assert "verified=error" not in (resp.headers.get("location") or "")


def test_absent_verify_token_still_missing_token() -> None:
    store = MagicMock()
    client = TestClient(_verify_app(store))
    resp = client.get("/auth/verify-email", follow_redirects=False)
    assert resp.status_code == 303
    assert "missing_token" in (resp.headers.get("location") or "")


def test_wellformed_unknown_verify_still_invalid_or_expired() -> None:
    store = MagicMock()
    client = TestClient(_verify_app(store))
    with patch(
        "dazzle.http.runtime.auth.email_verification_routes.validate_email_verification_token",
        return_value=None,
    ):
        resp = client.get(f"/auth/verify-email?token={_WELLFORMED_MISS}", follow_redirects=False)
    assert resp.status_code == 303
    loc = resp.headers.get("location") or ""
    assert "verified=error" in loc
    assert "invalid_or_expired" in loc


def _invite_app(store: MagicMock) -> FastAPI:
    app = FastAPI()
    app.state.auth_store = store
    app.state.sitespec = {}
    app.include_router(create_invitation_routes())
    return app


def test_leftover_invite_token_does_not_invent_invalid_page() -> None:
    store = MagicMock()
    client = TestClient(_invite_app(store))
    resp = client.get("/auth/accept-invite/zzz", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown invitation" in resp.text
    assert "already been used" not in resp.text


def test_leftover_invite_submit_does_not_invent_accept() -> None:
    store = MagicMock()
    client = TestClient(_invite_app(store))
    resp = client.post("/auth/accept-invite?token=ghost", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown invitation" in resp.text
    store.validate_session.assert_not_called()


def test_helper_source_pins_consume_token_leftover() -> None:
    magic = _MAGIC.read_text()
    assert "leftover_honest_auth_token" in magic
    assert "Unknown magic link" in magic
    assert "Magic link required" in magic
    assert "HTMLResponse" in magic
    reset = _RESET.read_text()
    assert "leftover_honest_auth_token" in reset
    assert "Unknown reset token" in reset
    assert "Reset token required" in reset
    verify = _VERIFY.read_text()
    assert "leftover_honest_auth_token" in verify
    assert "Unknown verification token" in verify
    invite = _INVITE.read_text()
    assert "leftover_honest_auth_token" in invite
    assert "Unknown invitation" in invite
    assert "Invitation required" in invite


def test_live_simple_task_declares_auth_login() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src


@pytest.mark.parametrize("junk", ["zzz", "ghost", "sid", "token:evil"])
def test_leftover_shapes_stay_put_on_magic(junk: str) -> None:
    store = MagicMock()
    client = TestClient(_magic_app(store))
    resp = client.get(f"/auth/magic/{junk}", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown magic link" in resp.text
