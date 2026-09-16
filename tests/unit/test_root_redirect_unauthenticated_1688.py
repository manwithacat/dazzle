"""Unauthenticated GET /app redirects to /login, not workspaces[0] (#1688)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dazzle.http.runtime.auth.models import AuthContext
from dazzle.http.runtime.page_routes import _root_redirect

pytestmark = pytest.mark.gate

_FALLBACK = "/app/workspaces/platform_console"
_PERSONA_ROUTES = {
    "super_admin": _FALLBACK,
    "teacher": "/app/workspaces/classroom",
}


def _req(path: str = "/app/") -> SimpleNamespace:
    return SimpleNamespace(url=SimpleNamespace(path=path))


@pytest.mark.asyncio
async def test_anonymous_root_redirects_to_login() -> None:
    deps = SimpleNamespace(get_auth_context=lambda _r: AuthContext(is_authenticated=False))
    resp = await _root_redirect(deps, _PERSONA_ROUTES, _FALLBACK, _req("/app/"))
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login?next=/app/"


@pytest.mark.asyncio
async def test_anonymous_root_preserves_path_in_next() -> None:
    deps = SimpleNamespace(get_auth_context=lambda _r: AuthContext())
    resp = await _root_redirect(deps, _PERSONA_ROUTES, _FALLBACK, _req("/app"))
    assert resp.headers["location"] == "/login?next=/app"


@pytest.mark.asyncio
async def test_no_auth_wired_still_uses_workspace_fallback() -> None:
    deps = SimpleNamespace(get_auth_context=None)
    resp = await _root_redirect(deps, _PERSONA_ROUTES, _FALLBACK, _req())
    assert resp.status_code == 302
    assert resp.headers["location"] == _FALLBACK


@pytest.mark.asyncio
async def test_authenticated_persona_still_lands_on_workspace() -> None:
    deps = SimpleNamespace(
        get_auth_context=lambda _r: AuthContext(is_authenticated=True, roles=["teacher"])
    )
    resp = await _root_redirect(deps, _PERSONA_ROUTES, _FALLBACK, _req())
    assert resp.headers["location"] == "/app/workspaces/classroom"
