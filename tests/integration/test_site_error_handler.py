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

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from dazzle.http.runtime.exception_handlers import register_site_error_handlers

_SITESPEC = {
    "brand": {"product_name": "TestApp"},
    "layout": {"nav": {"public": []}, "footer": {"columns": [], "disclaimer": ""}},
}


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
    resp = client.get("/raises-404", headers={"accept": "text/html"})
    assert resp.status_code == 404
    body = resp.text
    assert "404" in body
    assert "doesn" in body and "exist." in body
    assert "Go Home" in body
    assert "TestApp" in body
    # No Jinja templates fired — the marketing branch is fully typed.


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
    resp = client.get("/raises-403", headers={"accept": "text/html"})
    assert resp.status_code == 403
    body = resp.text
    assert "403" in body
    assert "denied" in body  # user-supplied message threaded through
    assert "Go to Dashboard" in body
    assert "Go Home" in body


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


# ───────────────── App-shell branch — typed (Phase 2.B full) ─────────────────


def test_app_path_404_renders_typed_app_view() -> None:
    """Phase 2.B full (v0.67.40): in-app 404 renders the typed
    `build_app_404_view` — no Jinja templates fire."""
    client = _build_app()
    resp = client.get("/app/raises-404", headers={"accept": "text/html"})
    assert resp.status_code == 404
    body = resp.text
    assert "404" in body
    assert "TestApp" in body
    assert "Go to Dashboard" in body


def test_app_path_403_renders_typed_app_view() -> None:
    client = _build_app()
    resp = client.get("/app/raises-403", headers={"accept": "text/html"})
    assert resp.status_code == 403
    body = resp.text
    assert "403" in body
    assert "Go to Dashboard" in body


def test_app_path_403_forbidden_detail_renders_panel() -> None:
    """The structured #808 detail still renders in the typed view —
    persona disclosure is the whole point of the in-app variant."""
    app = FastAPI()
    register_site_error_handlers(app, _SITESPEC)

    @app.get("/app/forbidden")
    def _f() -> None:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Insufficient role",
                "entity": "Task",
                "operation": "delete",
                "permitted_personas": ["admin"],
                "current_roles": ["viewer"],
            },
        )

    client = TestClient(app, follow_redirects=False)
    resp = client.get("/app/forbidden", headers={"accept": "text/html"})
    assert resp.status_code == 403
    body = resp.text
    assert "Insufficient role" in body
    assert "Entity: Task" in body
    assert "admin" in body
    assert "viewer" in body


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


# ───────────────── 500 handler (Phase 2.B partial) ─────────────────


def _build_500_app() -> TestClient:
    """Build an app that has a route which raises an unhandled exception.

    `debug=False` is required so the framework's typed 500 handler
    fires instead of re-raising into the test client.
    """
    app = FastAPI(debug=False)
    register_site_error_handlers(app, _SITESPEC)

    @app.get("/boom")
    def _boom() -> None:
        raise RuntimeError("internal db connection lost")

    @app.get("/app/boom")
    def _app_boom() -> None:
        raise RuntimeError("internal db connection lost")

    @app.get("/raises-500-http")
    def _raises_500_http() -> None:
        raise HTTPException(status_code=500, detail="explicit 500 raise")

    return TestClient(app, follow_redirects=False, raise_server_exceptions=False)


def test_site_500_unhandled_exception_renders_typed_view() -> None:
    """An uncaught exception in a route handler should render the
    typed 500 page for browser callers."""
    client = _build_500_app()
    resp = client.get("/boom", headers={"accept": "text/html"})
    assert resp.status_code == 500
    body = resp.text
    assert "500" in body
    assert "TestApp" in body
    assert "Try again" in body
    # Typed view, not Jinja.


def test_site_500_does_not_leak_exception_details_to_browser() -> None:
    """CWE-209: the exception's str() / repr / traceback must NOT
    surface in the HTML response body."""
    client = _build_500_app()
    resp = client.get("/boom", headers={"accept": "text/html"})
    assert resp.status_code == 500
    assert "internal db connection lost" not in resp.text
    assert "RuntimeError" not in resp.text
    assert "Traceback" not in resp.text


def test_site_500_json_for_api_callers() -> None:
    """API callers (no text/html accept) get a generic JSON 500."""
    client = _build_500_app()
    resp = client.get("/boom", headers={"accept": "application/json"})
    assert resp.status_code == 500
    # The framework returns a generic detail, NOT the original exception text.
    body = resp.json()
    assert body == {"detail": "Internal Server Error"}


def test_site_500_explicit_httpexception_renders_typed_view() -> None:
    """An HTTPException(500) (not just an uncaught raise) also
    routes through the typed view via the StarletteHTTPException
    handler branch."""
    client = _build_500_app()
    resp = client.get("/raises-500-http", headers={"accept": "text/html"})
    assert resp.status_code == 500
    body = resp.text
    assert "500" in body
    assert "Try again" in body


def test_site_500_app_path_renders_typed_app_view() -> None:
    """Phase 2.B full (v0.67.40): unhandled exception inside /app/*
    now renders the typed `build_app_500_view` — no longer falls
    through to Starlette's plain-text default."""
    client = _build_500_app()
    resp = client.get("/app/boom", headers={"accept": "text/html"})
    assert resp.status_code == 500
    body = resp.text
    assert "500" in body
    assert "TestApp" in body
    assert "Go to Dashboard" in body
    # CWE-209: even on the in-app path, the exception text must not leak.
    assert "internal db connection lost" not in body
    assert "RuntimeError" not in body


def test_site_500_uses_app_state_css_override() -> None:
    """Per-deployment CSS override threads through to the 500 page too."""
    app = FastAPI(debug=False)
    app.state.fragment_chrome_css_links = ("/my-tenant/custom.css",)
    register_site_error_handlers(app, _SITESPEC)

    @app.get("/boom")
    def _boom() -> None:
        raise RuntimeError("x")

    client = TestClient(app, follow_redirects=False, raise_server_exceptions=False)
    resp = client.get("/boom", headers={"accept": "text/html"})
    assert resp.status_code == 500
    assert "/my-tenant/custom.css" in resp.text
    assert "/static/dist/dazzle.min.css" not in resp.text
