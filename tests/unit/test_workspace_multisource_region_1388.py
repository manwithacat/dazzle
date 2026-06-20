"""Regression test for #1388 — multi-entity workspace regions
(`source: [A, B, ...]`, `display: tabbed_list`) 404'd at the
region-fetcher endpoint.

The dashboard card's lazy htmx fetch targets the BASE endpoint
``GET /api/workspaces/{ws}/regions/{region}`` (no source suffix),
but the route builder only registered the per-source sub-endpoints
``…/regions/{region}/{Entity}``. So the base request 404'd and the
tile rendered permanently broken — declared, validate-clean, dead at
runtime.

The fix registers the base endpoint too; it serves the TABBED_LIST
shell (the tab strip + per-tab hx-get to the sub-endpoints) and
fetches no items itself. A second gap surfaced once the route existed:
the render layer handed the adapter ``SourceTabContext`` objects but
the tabbed_list adapter only consumes dicts, so the shell rendered
"No tabs". The render boundary now normalises tabs to the dict shape.
"""

from __future__ import annotations


def _build_app_and_init_routes(dsl_src: str, tmp_path):
    from fastapi import FastAPI

    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules
    from dazzle.http.runtime.workspace_route_builder import WorkspaceRouteBuilder

    dsl_path = tmp_path / "app.dsl"
    dsl_path.write_text(dsl_src)
    modules = parse_modules([dsl_path])
    appspec = build_appspec(modules, "t")

    app = FastAPI()
    builder = WorkspaceRouteBuilder(
        app=app,
        appspec=appspec,
        entities=appspec.domain.entities,
        repositories={},
        auth_middleware=None,
        enable_auth=False,
        enable_test_mode=True,
    )
    builder.init_workspace_routes()
    return app


_MULTISOURCE_DSL = """module t
app t "Test"
entity Alpha:
  id: uuid pk
  name: str(100)
  status: str(20)
entity Beta:
  id: uuid pk
  name: str(100)
  status: str(20)
workspace dash "Dash":
  review_queue:
    source: [Alpha, Beta]
    display: tabbed_list
    filter_map:
      Alpha: status = review
      Beta: status = prepared
"""


def _route_paths(app) -> list[str]:
    return [getattr(r, "path", "") for r in app.routes]


def test_multisource_base_endpoint_registered(tmp_path) -> None:
    """The BASE region endpoint must be registered, not just the
    per-source sub-endpoints (the 404 root cause)."""
    app = _build_app_and_init_routes(_MULTISOURCE_DSL, tmp_path)
    paths = _route_paths(app)
    assert "/api/workspaces/dash/regions/review_queue" in paths, (
        "multi-source region's base endpoint must be registered (#1388) — "
        "the dashboard card's hx-get targets it with no source suffix"
    )
    # Per-source sub-endpoints still register (unchanged behaviour).
    assert "/api/workspaces/dash/regions/review_queue/Alpha" in paths
    assert "/api/workspaces/dash/regions/review_queue/Beta" in paths


def test_multisource_base_endpoint_serves_tab_strip(tmp_path) -> None:
    """The base endpoint serves 200 and renders the lazy tab strip
    with one tab per source entity — not a 404 and not a "No tabs"
    empty state."""
    from fastapi.testclient import TestClient

    app = _build_app_and_init_routes(_MULTISOURCE_DSL, tmp_path)
    client = TestClient(app)
    resp = client.get("/api/workspaces/dash/regions/review_queue")
    assert resp.status_code == 200, f"base endpoint 404'd/errored: {resp.status_code}"
    body = resp.text
    assert "No tabs" not in body, "tab strip rendered empty — SourceTabContext→dict gap (#1388)"
    assert 'role="tablist"' in body, "tabbed_list shell must emit a tablist"
    # Each per-source tab links to its sub-endpoint via hx-get.
    assert "/api/workspaces/dash/regions/review_queue/Alpha" in body
    assert "/api/workspaces/dash/regions/review_queue/Beta" in body
