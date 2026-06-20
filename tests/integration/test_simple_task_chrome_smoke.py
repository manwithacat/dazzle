"""Comprehensive route-walk smoke for simple_task with fragment_chrome=on.

The validation milestone for P17. Walks every GET route registered
by simple_task's page-route mounting and checks each for either:
  (a) Fragment-chrome success — 200 + `<body class="dz-page">`, or
  (b) acceptable degradation — 200 going through the legacy Jinja
      path (e.g. workspace routes that aren't yet Fragment-flipped),
      or
  (c) graceful 404 (path-param routes with bogus IDs).

Catches integration regressions the per-primitive tests can't see —
specifically, what happens when chrome=on meets a real app's full
URL surface area, not just the four flipped surfaces of the existing
test suite.

Routes that produce 5xx or other non-acceptable responses are listed
explicitly so the gap is visible. As the substrate grows to cover
those (workspaces in Phase 4, etc.) the lists move from `LEGACY` →
`FRAGMENT`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.core.appspec_loader import load_project_appspec

pytest.importorskip("dazzle.back.runtime.page_routes")
from dazzle.back.runtime.page_routes import create_page_routes  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_EXAMPLES = _REPO_ROOT / "examples"
_BOGUS_UUID = "00000000-0000-0000-0000-000000000000"


def _client_chrome_on(app_name: str = "simple_task") -> tuple[TestClient, FastAPI]:
    from dazzle.back.runtime.renderers.init import register_default_renderers
    from dazzle.back.runtime.services import RuntimeServices

    appspec = load_project_appspec(_EXAMPLES / app_name)
    fastapi_app = FastAPI()
    services = RuntimeServices()
    register_default_renderers(services)
    fastapi_app.state.services = services
    fastapi_app.state.fragment_chrome = True
    fastapi_app.include_router(create_page_routes(appspec, backend_url="http://127.0.0.1:9999"))
    return TestClient(fastapi_app), fastapi_app


def _resolve_route(template: str) -> str:
    """Substitute `{id}` (and any other path param) with a bogus UUID."""
    return re.sub(r"\{[^}]+\}", _BOGUS_UUID, template)


def _enumerate_get_routes(app: FastAPI) -> list[str]:
    """Every GET route registered by simple_task's page mounting,
    excluding FastAPI internals."""
    out: list[str] = []
    for r in app.routes:
        methods = getattr(r, "methods", None) or set()
        path = getattr(r, "path", None) or ""
        if "GET" not in methods:
            continue
        # Skip FastAPI's auto-generated routes
        if path.startswith("/openapi") or path.startswith("/docs") or path.startswith("/redoc"):
            continue
        out.append(path)
    return sorted(set(out))


# ─────────────────── Categorical assertions ───────────────────


def test_simple_task_chrome_smoke_routes_are_discoverable() -> None:
    """Sanity check: simple_task registers a meaningful number of
    routes. If this drops to 0, the smoke would silently no-op."""
    _, app = _client_chrome_on()
    routes = _enumerate_get_routes(app)
    assert len(routes) >= 20, (
        f"simple_task only exposed {len(routes)} GET routes; expected >=20. routes={routes!r}"
    )


def test_simple_task_chrome_smoke_no_route_returns_5xx() -> None:
    """Walk every GET route — none should produce a server error.
    404 is acceptable (bogus path params), 200 is acceptable.
    Anything else is a regression."""
    client, app = _client_chrome_on()
    failures: list[tuple[str, int, str]] = []
    for template in _enumerate_get_routes(app):
        url = _resolve_route(template)
        resp = client.get(url)
        if resp.status_code >= 500:
            failures.append((url, resp.status_code, resp.text[:300]))
    assert not failures, f"server errors on {len(failures)} routes:\n{failures!r}"


def test_simple_task_chrome_smoke_categorise_routes_by_render_path() -> None:
    """Walk every route; categorise by whether it goes through
    Fragment chrome (`<body class="dz-page">`) or stays on the legacy
    Jinja path. The categorisation is a snapshot — as more pieces
    flip, the FRAGMENT set grows and LEGACY shrinks. Use the lists
    in the assertion message to track Phase 4+ progress."""
    client, app = _client_chrome_on()
    fragment: list[str] = []
    legacy: list[str] = []
    not_found: list[str] = []
    forbidden: list[str] = []
    redirect: list[str] = []
    other: list[tuple[str, int]] = []
    for template in _enumerate_get_routes(app):
        url = _resolve_route(template)
        resp = client.get(url, follow_redirects=False)
        code = resp.status_code
        if code == 404:
            not_found.append(template)
            continue
        if code == 403:
            # RBAC scope filtering — auth-gated routes return 403 in
            # the unauthenticated test client. Correct behaviour, not
            # a chrome failure. The 403 response itself doesn't go
            # through the Fragment chrome path (framework-level error
            # rendering, separate from page render).
            forbidden.append(template)
            continue
        if code in (301, 302, 303, 307, 308):
            redirect.append(template)
            continue
        if code != 200:
            other.append((template, code))
            continue
        if '<body class="dz-page">' in resp.text:
            fragment.append(template)
        else:
            legacy.append(template)
    # Snapshot: surface routes (entity list/detail/create/edit) should
    # be on Fragment; workspaces are still on Jinja (Phase 4 scope).
    assert fragment, (
        f"no routes routed through Fragment chrome — chrome dispatch broken? "
        f"legacy={legacy!r}, not_found={not_found!r}, "
        f"forbidden={forbidden!r}, other={other!r}"
    )
    # 200 / 404 / 403 / 3xx are all acceptable; anything else is a
    # regression (5xx is caught by the dedicated test above; this
    # guards against unexpected 4xx values).
    assert not other, f"unexpected status codes: {other!r}"


def test_simple_task_chrome_primary_surfaces_all_on_fragment() -> None:
    """The four primary surface modes — list, view, create, edit —
    on the Task entity all route through Fragment chrome."""
    client, _ = _client_chrome_on()
    for url in (
        "/task",  # list
        "/task/create",  # create
        f"/task/{_BOGUS_UUID}",  # view (404 acceptable)
        f"/task/{_BOGUS_UUID}/edit",  # edit (404 acceptable)
    ):
        resp = client.get(url)
        if resp.status_code == 404:
            continue  # legitimate — bogus UUID
        assert resp.status_code == 200, (
            f"GET {url}: status {resp.status_code}, body[:300]={resp.text[:300]!r}"
        )
        assert '<body class="dz-page">' in resp.text, (
            f"GET {url} returned 200 but not via Fragment chrome. body[:500]={resp.text[:500]!r}"
        )


def test_simple_task_chrome_root_route_renders() -> None:
    """The root `/` route must serve — typically a redirect or the
    primary entity list. Either is acceptable; what's not is a 5xx."""
    client, _ = _client_chrome_on()
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (200, 301, 302, 303, 307, 308, 404), (
        f"GET / unexpected status {resp.status_code}, body[:200]={resp.text[:200]!r}"
    )


def test_simple_task_chrome_workspace_routes_dont_crash() -> None:
    """Workspace routes use a separate render path (workspace_renderer.py)
    — they're Phase 4 scope, not yet on Fragment chrome. Pin that they
    return cleanly (no 5xx) even when chrome=on. As Phase 4 lands,
    extend this test to assert dz-page presence."""
    client, _ = _client_chrome_on()
    workspace_urls = (
        "/workspaces/task_board",
        "/workspaces/admin_dashboard",
        "/workspaces/team_overview",
        "/workspaces/my_work",
    )
    for url in workspace_urls:
        resp = client.get(url)
        assert resp.status_code < 500, (
            f"GET {url} produced server error {resp.status_code}: body[:300]={resp.text[:300]!r}"
        )
