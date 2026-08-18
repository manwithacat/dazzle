"""OAuth leftover code/state must not invent sso_failed (cycle 2243).

leftover-honest consume token / 2FA code already exist (oral #109 /
#108). SSO callback still forwarded leftover ``?code=zzz`` / ``ghost``
into authorize_access_token and invented ``303 /login?error=sso_failed``.
The same leftover on GET ``/auth/enterprise/callback`` invented the
same theater. Leftover ``?state=zzz`` did too. Valid opaque IdP codes
(urlsafe + ``/+=.``, length 16–512) ride; leftover stays put (400, no
theater). Absent / blank still first-visit (stray / cancel still
sso_failed). Well-formed codes that fail exchange still bounce
sso_failed. Live simple_task ``/auth/sso/{provider}/callback``.
Oral #113 — not leftover consume token (oral #109), not leftover 2FA
code (oral #108), not leftover SSO provider (oral #112), not leftover
``?connection=`` (oral #110).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from dazzle.http.runtime.auth.enterprise_routes import create_enterprise_sso_routes
from dazzle.http.runtime.auth.leftover_oauth_code import leftover_honest_oauth_code
from dazzle.http.runtime.auth.sso_config import SsoProviderConfig
from dazzle.http.runtime.auth.sso_routes import create_sso_routes

_HELPER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "leftover_oauth_code.py"
)
_SSO = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "sso_routes.py"
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
_VIEWS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "sso_views.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "simple_task" / "dazzle.toml"

_VALID = "A" * 32
_GOOGLE_SHAPED = "4/0Aean5QxYz0123456789"
_WELLFORMED_MISS = "B" * 32


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (_VALID, _VALID),
        (_GOOGLE_SHAPED, _GOOGLE_SHAPED),
        ("C" * 16, "C" * 16),
        ("", ""),
        (None, ""),
        ("   ", ""),
        ("zzz", None),
        ("ghost", None),
        ("fake-code", None),
        ("x", None),
        ("not-a-code", None),
        (["A" * 32], None),
        ({"code": _VALID}, None),
        (1, None),
        (True, None),
    ],
    ids=[
        "urlsafe-32",
        "google-slash",
        "min-16",
        "empty-default",
        "none-default",
        "blank-default",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-fake-code",
        "leftover-short",
        "leftover-dashed-words",
        "leftover-list",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
    ],
)
def test_leftover_honest_oauth_code_does_not_invent(raw: object, expected: str | None) -> None:
    assert leftover_honest_oauth_code(raw) == expected


def _google() -> SsoProviderConfig:
    return SsoProviderConfig(
        name="google",
        display_name="Google",
        client_id="cid",
        client_secret="csecret",
        discovery_url="https://accounts.google.com/.well-known/openid-configuration",
        scopes="openid email profile",
    )


class _RaisingOAuth:
    async def authorize_access_token(self, request: object) -> dict[str, object]:
        raise RuntimeError("exchange miss")


def _sso_app(*, raising: bool = False) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret", same_site="lax")
    app.state.sso_providers = (_google(),)
    app.state.auth_store = MagicMock()
    if raising:
        app.state._sso_clients = {"google": _RaisingOAuth()}
    app.include_router(create_sso_routes())
    return app


def _enterprise_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret", same_site="lax")
    store = MagicMock()
    store.get_connection.return_value = None
    app.state.auth_store = store
    app.include_router(create_enterprise_sso_routes())
    return app


def test_leftover_sso_code_does_not_invent_sso_failed() -> None:
    client = TestClient(_sso_app())
    resp = client.get("/auth/sso/google/callback?code=zzz", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown authorization code" in resp.text
    assert "sso_failed" not in (resp.headers.get("location") or "")


def test_leftover_sso_ghost_code_does_not_invent_sso_failed() -> None:
    client = TestClient(_sso_app())
    resp = client.get("/auth/sso/google/callback?code=ghost", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown authorization code" in resp.text


def test_leftover_sso_state_does_not_invent_sso_failed() -> None:
    client = TestClient(_sso_app())
    resp = client.get(
        f"/auth/sso/google/callback?code={_VALID}&state=zzz",
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Unknown OAuth state" in resp.text
    assert "sso_failed" not in (resp.headers.get("location") or "")


def test_leftover_enterprise_code_does_not_invent_sso_failed() -> None:
    client = TestClient(_enterprise_app())
    resp = client.get("/auth/enterprise/callback?code=zzz", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown authorization code" in resp.text
    assert "sso_failed" not in (resp.headers.get("location") or "")


def test_absent_code_still_first_visit() -> None:
    client = TestClient(_sso_app(raising=True))
    resp = client.get("/auth/sso/google/callback", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=sso_failed"


def test_wellformed_exchange_miss_still_sso_failed() -> None:
    client = TestClient(_sso_app(raising=True))
    resp = client.get(
        f"/auth/sso/google/callback?code={_WELLFORMED_MISS}",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=sso_failed"


def test_helper_source_pins_oauth_code_leftover() -> None:
    helper = _HELPER.read_text()
    sso = _SSO.read_text()
    enterprise = _ENTERPRISE.read_text()
    assert "def leftover_honest_oauth_code" in helper
    assert "_OAUTH_CODE" in helper
    assert "leftover_honest_oauth_code" in sso
    assert "leftover_honest_oauth_code" in enterprise
    assert "Unknown authorization code" in sso
    assert "Unknown OAuth state" in sso
    assert "Unknown authorization code" in enterprise
    assert "Unknown OAuth state" in enterprise
    assert "HTMLResponse" in sso
    assert "HTMLResponse" in enterprise
    assert "Response(\n            status_code=400,\n            content=" not in sso
    assert "Response(\n            status_code=400,\n            content=" not in enterprise


def test_live_login_buttons_name_sso_callback_path() -> None:
    src = _VIEWS.read_text()
    assert "/auth/sso/{provider.name}" in src
    live = _LIVE.read_text()
    assert "[auth]" in live
