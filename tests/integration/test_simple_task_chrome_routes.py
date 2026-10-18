"""Route walk over ``examples/simple_task`` with ``fragment_chrome`` on.

Catches what per-primitive tests cannot: what happens when chrome=on meets a
real app's full GET surface. Path params are filled with a bogus UUID, so 404
is a legitimate answer; 403 is RBAC on the unauthenticated client; 3xx is a
redirect. Jinja2 left the project in v0.67.118 (#1042), so "zero Jinja" is
structural and the walk pins status shapes plus the Fragment chrome marker.
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
from dazzle.http.runtime.renderers.init import register_default_renderers  # noqa: E402
from dazzle.http.runtime.route_validator import iter_http_route_contexts  # noqa: E402
from dazzle.http.runtime.services import RuntimeServices  # noqa: E402

_SIMPLE_TASK = Path(__file__).resolve().parents[2] / "examples" / "simple_task"
_BOGUS_UUID = "00000000-0000-0000-0000-000000000000"
_FRAGMENT_BODY = '<body class="dz-page">'
_REDIRECTS = {301, 302, 303, 307, 308}


@pytest.fixture(scope="module")
def chrome_app() -> tuple[TestClient, FastAPI]:
    app = FastAPI()
    services = RuntimeServices()
    register_default_renderers(services)
    app.state.services = services
    app.state.fragment_chrome = True
    app.include_router(create_page_routes(load_project_appspec(_SIMPLE_TASK)))
    return TestClient(app), app


def _get_routes(app: FastAPI) -> list[str]:
    """Every GET route the page mounting registers, minus FastAPI's docs routes."""
    paths = {
        ctx.path or ""
        for ctx in iter_http_route_contexts(app)
        if "GET" in (ctx.methods or set())
        and not (ctx.path or "").startswith(("/openapi", "/docs", "/redoc"))
    }
    return sorted(paths)


def _resolve(template: str) -> str:
    return re.sub(r"\{[^}]+\}", _BOGUS_UUID, template)


def test_every_get_route_answers_with_an_acceptable_status(
    chrome_app: tuple[TestClient, FastAPI],
) -> None:
    """200 / 3xx / 403 / 404 only; redirects followed must not 5xx; at least
    one route is served through Fragment chrome (else dispatch is broken)."""
    client, app = chrome_app
    routes = _get_routes(app)
    # Guard against the walk silently no-op'ing.
    assert len(routes) >= 20, f"simple_task exposed only {len(routes)} GET routes: {routes!r}"
    unexpected: list[tuple[str, int]] = []
    fragment: list[str] = []
    for template in routes:
        url = _resolve(template)
        resp = client.get(url, follow_redirects=False)
        if resp.status_code in _REDIRECTS:
            followed = client.get(url)
            if followed.status_code >= 500:
                unexpected.append((template, followed.status_code))
        elif resp.status_code not in (200, 403, 404):
            unexpected.append((template, resp.status_code))
        elif resp.status_code == 200 and _FRAGMENT_BODY in resp.text:
            fragment.append(template)
    assert not unexpected, f"unexpected status codes: {unexpected!r}"
    assert fragment, "no route rendered through Fragment chrome"


@pytest.mark.parametrize(
    "url",
    [
        "/task",
        "/task/create",
        f"/task/{_BOGUS_UUID}",
        f"/task/{_BOGUS_UUID}/edit",
        "/taskcomment",
        "/taskcomment/create",
    ],
    ids=[
        "task-list",
        "task-create",
        "task-view",
        "task-edit",
        "taskcomment-list",
        "taskcomment-create",
    ],
)
def test_primary_surface_renders_through_fragment_chrome(
    chrome_app: tuple[TestClient, FastAPI], url: str
) -> None:
    client, _ = chrome_app
    resp = client.get(url)
    if resp.status_code == 404:
        return  # bogus UUID on view/edit
    assert resp.status_code == 200, f"GET {url}: {resp.status_code} {resp.text[:300]!r}"
    assert _FRAGMENT_BODY in resp.text, f"GET {url} bypassed Fragment chrome: {resp.text[:500]!r}"


def test_htmx_partial_request_serves_the_list(chrome_app: tuple[TestClient, FastAPI]) -> None:
    """A content-slot request takes the P8 short-circuit (inner HTML, no page
    chrome); htmx 4 sends the target as `tag#id` (#1818)."""
    client, _ = chrome_app
    resp = client.get("/task", headers={"HX-Request": "true", "HX-Target": "main#main-content"})
    assert resp.status_code == 200
    assert _FRAGMENT_BODY not in resp.text


@pytest.mark.parametrize(
    "url",
    [
        "/",
        "/workspaces/task_board",
        "/workspaces/admin_dashboard",
        "/workspaces/team_overview",
        "/workspaces/my_work",
    ],
)
def test_root_and_workspace_routes_do_not_crash(
    chrome_app: tuple[TestClient, FastAPI], url: str
) -> None:
    client, _ = chrome_app
    resp = client.get(url, follow_redirects=False)
    assert resp.status_code < 500, f"GET {url}: {resp.status_code} {resp.text[:300]!r}"
