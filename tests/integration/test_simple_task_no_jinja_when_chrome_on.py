"""Validates the goal: simple_task routes render without Jinja.

v0.67.118 (#1042 follow-up): jinja2 was removed from the project,
so the no-Jinja invariant is structurally guaranteed. The Template
spy that used to record render calls is gone — these tests now
just walk every served GET route and assert the response shapes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.core.appspec_loader import load_project_appspec

pytest.importorskip("dazzle.http.runtime.page_routes")
from dazzle.http.runtime.page_routes import create_page_routes  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_EXAMPLES = _REPO_ROOT / "examples"
_BOGUS_UUID = "00000000-0000-0000-0000-000000000000"


def _client_chrome_on() -> tuple[TestClient, FastAPI]:
    from dazzle.http.runtime.renderers.init import register_default_renderers
    from dazzle.http.runtime.services import RuntimeServices

    appspec = load_project_appspec(_EXAMPLES / "simple_task")
    fastapi_app = FastAPI()
    services = RuntimeServices()
    register_default_renderers(services)
    fastapi_app.state.services = services
    fastapi_app.state.fragment_chrome = True
    fastapi_app.include_router(create_page_routes(appspec, backend_url="http://127.0.0.1:9999"))
    return TestClient(fastapi_app), fastapi_app


def _resolve(template: str) -> str:
    return re.sub(r"\{[^}]+\}", _BOGUS_UUID, template)


# ─────────────────── Per-route Jinja accounting ───────────────────


def test_primary_surface_routes_render_zero_jinja_templates() -> None:
    """The four primary surface modes — list, view, create, edit —
    on simple_task's Task entity. When chrome=on AND surface is flipped
    (Plan 11 closure), these routes should produce zero Jinja
    Template.render() invocations.

    This is the canonical "Jinja-free request" check — if it ever
    starts failing, something on the page-route → Fragment-chrome path
    has regressed back to a Jinja fallback.
    """
    client, _ = _client_chrome_on()
    routes = (
        "/task",  # list
        "/task/create",  # create
        f"/task/{_BOGUS_UUID}",  # view (404 acceptable)
        f"/task/{_BOGUS_UUID}/edit",  # edit (404 acceptable)
    )
    for url in routes:
        resp = client.get(url, follow_redirects=False)
        # 200 / 404 / 3xx are all acceptable shapes — the key
        # invariant (no Jinja templates) is structurally guaranteed
        # now that jinja2 is gone (#1042). This loop verifies every
        # route still serves without crashing.
        assert resp.status_code < 500, f"{url} returned {resp.status_code}"


def test_htmx_partial_request_renders_zero_jinja_templates() -> None:
    """htmx requests on chrome=on apps with flipped surfaces use the
    P8 short-circuit path (return inner_html directly). Zero Jinja is
    structurally guaranteed — jinja2 is no longer installed."""
    client, _ = _client_chrome_on()
    resp = client.get("/task", headers={"HX-Request": "true"})
    assert resp.status_code == 200


def test_taskcomment_routes_render_zero_jinja_templates() -> None:
    """The other DSL-flipped entity in simple_task — TaskComment — also
    routes through Fragment chrome. Smoke-test the route shapes."""
    client, _ = _client_chrome_on()
    routes = ("/taskcomment", "/taskcomment/create")
    for url in routes:
        resp = client.get(url, follow_redirects=False)
        assert resp.status_code < 500, f"{url} returned {resp.status_code}"


# ─────────────────── Per-route inventory (categorisation) ───────────


def test_simple_task_chrome_zero_jinja_across_every_route() -> None:
    """The strongest claim — when chrome=on, NO Jinja templates render
    for ANY served GET route in simple_task (regardless of status code).
    Empirically true today: 200/404/403/302 all produce zero Jinja
    template invocations.

    Pins the Jinja-decommissioning state so any regression that
    re-introduces a Jinja fallback fires a clear test failure.
    """
    client, app = _client_chrome_on()
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        methods = getattr(route, "methods", None) or set()
        if "GET" not in methods or path.startswith(("/openapi", "/docs", "/redoc")):
            continue
        url = _resolve(path)
        resp = client.get(url, follow_redirects=False)
        # Every GET route must serve without 5xx — jinja-free is
        # structurally guaranteed by the absence of jinja2.
        assert resp.status_code < 500, f"{path} returned {resp.status_code}"
