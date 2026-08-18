"""SSO leftover provider slug must not invent sso_provider_unknown (cycle 2242).

leftover-honest catalog already exists (oral #69 / leftover_honest_auth_error).
``GET /auth/sso/{provider}`` still forwarded leftover ``zzz`` / ``ghost``
into get_provider and invented ``303 /login?error=sso_provider_unknown``.
The same leftover on GET callback invented the same theater. Valid
``google`` / ``microsoft`` ride; leftover stays put (400, no theater).
Absent / blank still first-visit. Well-formed slugs that are not
configured still bounce sso_provider_unknown. Live login
``/auth/sso/{provider}`` (sso_views Continue-with). Oral #112 — not
leftover ``?connection=`` (oral #110), not leftover ``?new=`` (oral
#97), not leftover catalog picker (oral #69).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from dazzle.http.runtime.auth.leftover_sso_provider import leftover_honest_sso_provider
from dazzle.http.runtime.auth.sso_config import SSO_PROVIDER_TOKENS, SsoProviderConfig
from dazzle.http.runtime.auth.sso_routes import create_sso_routes

_HELPER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "leftover_sso_provider.py"
)
_ROUTES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "sso_routes.py"
)
_CONFIG = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "sso_config.py"
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


def _google() -> SsoProviderConfig:
    return SsoProviderConfig(
        name="google",
        display_name="Google",
        client_id="cid",
        client_secret="csecret",
        discovery_url="https://accounts.google.com/.well-known/openid-configuration",
        scopes="openid email profile",
    )


def _sso_app(*, configured: bool = True) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret", same_site="lax")
    app.state.sso_providers = (_google(),) if configured else ()
    app.state.auth_store = MagicMock()
    app.include_router(create_sso_routes())
    return app


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("google", "google"),
        ("microsoft", "microsoft"),
        ("", ""),
        (None, ""),
        ("   ", ""),
        ("zzz", None),
        ("ghost", None),
        ("unknown-provider", None),
        ("bogus", None),
        ("github", None),
        ("Google", None),
        ("google ", "google"),
        (["google"], None),
        ({"name": "google"}, None),
        (1, None),
        (True, None),
    ],
    ids=[
        "valid-google",
        "valid-microsoft",
        "empty-default",
        "none-default",
        "blank-default",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-unknown-provider",
        "leftover-bogus",
        "leftover-github",
        "leftover-title-case",
        "valid-strip",
        "leftover-list",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
    ],
)
def test_leftover_honest_sso_provider_does_not_invent(raw: object, expected: str | None) -> None:
    assert leftover_honest_sso_provider(raw) == expected


def test_leftover_initiate_does_not_invent_sso_provider_unknown() -> None:
    client = TestClient(_sso_app())
    resp = client.get("/auth/sso/zzz", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown SSO provider" in resp.text
    assert "sso_provider_unknown" not in (resp.headers.get("location") or "")


def test_leftover_initiate_ghost_does_not_invent_sso_provider_unknown() -> None:
    client = TestClient(_sso_app())
    resp = client.get("/auth/sso/ghost", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown SSO provider" in resp.text


def test_leftover_callback_does_not_invent_sso_provider_unknown() -> None:
    client = TestClient(_sso_app())
    resp = client.get("/auth/sso/bogus/callback?code=x", follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown SSO provider" in resp.text
    assert "sso_provider_unknown" not in (resp.headers.get("location") or "")


def test_wellformed_unconfigured_still_sso_provider_unknown() -> None:
    client = TestClient(_sso_app(configured=False))
    resp = client.get("/auth/sso/google", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=sso_provider_unknown"


def test_wellformed_unconfigured_callback_still_sso_provider_unknown() -> None:
    client = TestClient(_sso_app(configured=False))
    resp = client.get("/auth/sso/microsoft/callback?code=x", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=sso_provider_unknown"


def test_helper_source_pins_sso_provider_leftover() -> None:
    helper = _HELPER.read_text()
    routes = _ROUTES.read_text()
    config = _CONFIG.read_text()
    views = _VIEWS.read_text()
    assert "def leftover_honest_sso_provider" in helper
    assert "leftover_honest_auth_error" in helper
    assert "SSO_PROVIDER_TOKENS" in helper
    assert "SSO_PROVIDER_TOKENS" in config
    assert '("google", "microsoft")' in config
    assert SSO_PROVIDER_TOKENS == ("google", "microsoft")
    assert "leftover_honest_sso_provider" in routes
    assert "Unknown SSO provider" in routes
    assert "HTMLResponse" in routes
    assert routes.count("leftover_honest_sso_provider") >= 2
    assert "/auth/sso/{provider.name}" in views


def test_live_login_buttons_name_sso_provider_path() -> None:
    src = _VIEWS.read_text()
    assert "/auth/sso/{provider.name}" in src
