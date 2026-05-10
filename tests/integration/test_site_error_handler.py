"""Phase 2.A (v0.67.34) integration tests for the typed-Fragment
marketing-site 403/404 error handlers.

Coverage:
  1. A 404 raised on a non-/app path renders the typed
     `build_site_404_view` output (no Jinja templates fired).
  2. A 403 raised on a non-/app path renders the typed
     `build_site_403_view` output, with the user's message threaded
     through.
  3. The app-shell branch (path starts with `/app/`) still routes
     to the Jinja `app/404.html` / `app/403.html` templates — that
     migration is part of a future ship.
  4. JSON requests (Accept: application/json) still receive JSON
     error bodies regardless of the migration.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from jinja2 import Template

from dazzle_back.runtime.exception_handlers import register_site_error_handlers

_SITESPEC = {
    "brand": {"product_name": "TestApp"},
    "layout": {"nav": {"public": []}, "footer": {"columns": [], "disclaimer": ""}},
}


class _JinjaSpy:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._original = Template.render

    def __enter__(self) -> _JinjaSpy:
        spy = self
        original = self._original

        def tracked(self_t: Template, *a: object, **kw: object) -> str:
            name = getattr(self_t, "name", None) or "<inline>"
            spy.calls.append(name)
            return original(self_t, *a, **kw)

        self._patch = patch.object(Template, "render", tracked)
        self._patch.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._patch.stop()


def _build_app() -> TestClient:
    app = FastAPI()
    register_site_error_handlers(app, _SITESPEC)

    @app.get("/raises-404")
    def _r404() -> None:
        raise HTTPException(status_code=404, detail="not found")

    @app.get("/raises-403")
    def _r403() -> None:
        raise HTTPException(status_code=403, detail="denied")

    @app.get("/app/raises-404")
    def _r404_app() -> None:
        raise HTTPException(status_code=404, detail="app not found")

    @app.get("/app/raises-403")
    def _r403_app() -> None:
        raise HTTPException(status_code=403, detail="app denied")

    return TestClient(app, follow_redirects=False)


# ───────────────── Marketing 404 (non-/app paths) ─────────────────


def test_site_404_browser_renders_typed_view() -> None:
    client = _build_app()
    with _JinjaSpy() as spy:
        resp = client.get("/raises-404", headers={"accept": "text/html"})
    assert resp.status_code == 404
    body = resp.text
    assert "404" in body
    assert "doesn" in body and "exist." in body
    assert "Go Home" in body
    assert "TestApp" in body
    # No Jinja templates fired — the marketing branch is fully typed.
    assert spy.calls == []


def test_site_404_unknown_path_renders_typed_view() -> None:
    """A truly unhandled path (no matching route) also hits the
    starlette 404 handler and should render the typed view."""
    client = _build_app()
    resp = client.get("/no/such/path", headers={"accept": "text/html"})
    assert resp.status_code == 404
    assert "404" in resp.text


def test_site_404_json_returns_json() -> None:
    """JSON callers still get JSON — only browser requests get HTML."""
    client = _build_app()
    resp = client.get("/raises-404", headers={"accept": "application/json"})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "not found"}


# ───────────────── Marketing 403 (non-/app paths) ─────────────────


def test_site_403_browser_renders_typed_view() -> None:
    client = _build_app()
    with _JinjaSpy() as spy:
        resp = client.get("/raises-403", headers={"accept": "text/html"})
    assert resp.status_code == 403
    body = resp.text
    assert "403" in body
    assert "denied" in body  # user-supplied message threaded through
    assert "Go to Dashboard" in body
    assert "Go Home" in body
    assert spy.calls == []


def test_site_403_default_message_when_detail_missing() -> None:
    """When `HTTPException(403)` is raised without `detail`, FastAPI
    auto-fills `detail="Forbidden"`. The typed view threads that
    string through verbatim as the human-readable message."""
    app = FastAPI()
    register_site_error_handlers(app, _SITESPEC)

    @app.get("/raises-bare-403")
    def _bare() -> None:
        raise HTTPException(status_code=403)

    client = TestClient(app, follow_redirects=False)
    resp = client.get("/raises-bare-403", headers={"accept": "text/html"})
    assert resp.status_code == 403
    assert "Forbidden" in resp.text


def test_site_403_json_returns_json() -> None:
    client = _build_app()
    resp = client.get("/raises-403", headers={"accept": "application/json"})
    assert resp.status_code == 403
    assert resp.json() == {"detail": "denied"}


# ───────────────── App-shell branch still on Jinja ─────────────────


def test_app_path_404_still_renders_jinja_app_shell() -> None:
    """In-app 404s render via the existing Jinja `app/404.html`
    template — that migration is out of scope for Phase 2.A."""
    client = _build_app()
    with _JinjaSpy() as spy:
        resp = client.get("/app/raises-404", headers={"accept": "text/html"})
    assert resp.status_code == 404
    # The app-shell layout fires its Jinja template + ancestors.
    assert any("app/404.html" in c for c in spy.calls)


def test_app_path_403_still_renders_jinja_app_shell() -> None:
    client = _build_app()
    with _JinjaSpy() as spy:
        resp = client.get("/app/raises-403", headers={"accept": "text/html"})
    assert resp.status_code == 403
    assert any("app/403.html" in c for c in spy.calls)


# ───────────────── Asset overrides ─────────────────


def test_site_404_uses_app_state_css_override() -> None:
    """Per-deployment CSS override on `app.state.fragment_chrome_css_links`
    threads through to the rendered typed view."""
    app = FastAPI()
    app.state.fragment_chrome_css_links = ("/my-tenant/custom.css",)
    register_site_error_handlers(app, _SITESPEC)

    @app.get("/r")
    def _r() -> None:
        raise HTTPException(status_code=404)

    client = TestClient(app, follow_redirects=False)
    resp = client.get("/r", headers={"accept": "text/html"})
    assert resp.status_code == 404
    assert "/my-tenant/custom.css" in resp.text
    assert "/static/dist/dazzle.min.css" not in resp.text


def test_site_403_default_css_when_no_override() -> None:
    """No app.state override → framework-default minified bundle."""
    client = _build_app()
    resp = client.get("/raises-403", headers={"accept": "text/html"})
    assert resp.status_code == 403
    assert "/static/dist/dazzle.min.css" in resp.text
