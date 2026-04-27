"""Regression test for #907 — bodyless authored display modes
(action_grid, pipeline_steps, status_list, confirm_action_panel)
must get a route registered even though they have no `source:`.

The pre-fix code in `WorkspaceRouteBuilder.init_workspace_routes`
short-circuited via `if not ctx_region.source: continue` — which
silently skipped registration for any sourceless region. Result:
the HTMX endpoint 404'd, the skeleton placeholder never got
replaced, the entries never rendered. AegisMark's
sims_sync_settings_workspace hit this on three consecutive
status_list regions before reporting it.

The fix exempts the four bodyless display modes from the early
bail. The handler downstream short-circuits the items fetch when
source is None and renders the template from the IR's authored
config (entries / stages / cards / confirmations etc.).
"""

from __future__ import annotations


def _build_app_and_init_routes(dsl_src: str, tmp_path):
    """Helper: parse DSL via the standard parse_modules pipeline,
    build_appspec, then init the route builder. Returns the FastAPI
    app so tests can inspect `app.routes` for the expected paths."""
    from fastapi import FastAPI

    from dazzle.core.linker import build_appspec
    from dazzle.core.parser import parse_modules
    from dazzle_back.runtime.workspace_route_builder import WorkspaceRouteBuilder

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


def _route_paths(app) -> list[str]:
    return [getattr(r, "path", "") for r in app.routes]


# ───────────────────────── one test per bodyless display ──────────────────────────


class TestSourcelessRoutesRegistered:
    """Each of the four bodyless display modes must get a route at
    /api/workspaces/<ws>/regions/<region> even with no source."""

    def test_action_grid_sourceless(self, tmp_path) -> None:
        src = """module t
app t "Test"
workspace dash "Dash":
  cta:
    display: action_grid
    actions:
      - label: "Do thing"
        action: thing_create
"""
        app = _build_app_and_init_routes(src, tmp_path)
        paths = _route_paths(app)
        assert "/api/workspaces/dash/regions/cta" in paths, (
            "action_grid sourceless region missing route — #907 regression. "
            f"Routes: {[p for p in paths if 'workspaces' in p]}"
        )

    def test_pipeline_steps_sourceless(self, tmp_path) -> None:
        src = """module t
app t "Test"
workspace dash "Dash":
  ingestion:
    display: pipeline_steps
    stages:
      - label: "Scanned"
        value: "Daily 02:00 UTC"
"""
        app = _build_app_and_init_routes(src, tmp_path)
        paths = _route_paths(app)
        assert "/api/workspaces/dash/regions/ingestion" in paths, (
            "pipeline_steps sourceless region missing route — #907 regression"
        )

    def test_status_list_sourceless(self, tmp_path) -> None:
        """The originally-reported case from #907."""
        src = """module t
app t "Test"
workspace dash "Dash":
  legal_basis_gates:
    display: status_list
    entries:
      - title: "DPA signed"
        caption: "Oakwood Academy / DPA v1.4"
        icon: "file-check"
        state: positive
"""
        app = _build_app_and_init_routes(src, tmp_path)
        paths = _route_paths(app)
        assert "/api/workspaces/dash/regions/legal_basis_gates" in paths, (
            "status_list sourceless region missing route — original #907 case"
        )

    def test_confirm_action_panel_sourceless(self, tmp_path) -> None:
        src = """module t
app t "Test"
workspace dash "Dash":
  authorise:
    display: confirm_action_panel
    confirmations:
      - title: "I agree"
    primary_action: do_thing
"""
        app = _build_app_and_init_routes(src, tmp_path)
        paths = _route_paths(app)
        assert "/api/workspaces/dash/regions/authorise" in paths, (
            "confirm_action_panel sourceless region missing route — #907 regression"
        )


# ───────────────────────── existing behaviour preserved ──────────────────────────


class TestSourcedRoutesStillRegister:
    """Defensive: the fix exempts only the four bodyless modes from
    the source-required check. Sourced regions in any display mode
    must still register exactly as before."""

    def test_list_with_source_registers(self, tmp_path) -> None:
        src = """module t
app t "Test"
entity Item:
  id: uuid pk
  name: str(100)
workspace dash "Dash":
  items:
    source: Item
    display: list
"""
        app = _build_app_and_init_routes(src, tmp_path)
        paths = _route_paths(app)
        assert "/api/workspaces/dash/regions/items" in paths


# ───────────────────────── still skip non-bodyless sourceless ──────────────────────────


class TestNonBodylessSourcelessSkipped:
    """The exemption is narrow — only the four named display modes
    get the route. A sourceless `display: list` (which doesn't make
    sense) must still be skipped, not registered."""

    def test_list_without_source_skipped(self) -> None:
        # display: list with no source isn't a meaningful region.
        # Pre-fix it was skipped via the early-bail; post-fix it must
        # still be skipped because LIST isn't in the bodyless allowlist.
        # The parser would normally reject this with the "requires
        # source: or aggregate:" error, so we have to construct the
        # situation programmatically rather than via DSL.
        from fastapi import FastAPI

        from dazzle.core.ir import (
            AppSpec,
            DisplayMode,
            DomainSpec,
            WorkspaceRegion,
            WorkspaceSpec,
        )
        from dazzle_back.runtime.workspace_route_builder import WorkspaceRouteBuilder

        # Hand-build a minimal AppSpec with a sourceless LIST region
        # (bypasses the parser's bodyless-region check).
        region = WorkspaceRegion(name="orphan", display=DisplayMode.LIST)
        ws = WorkspaceSpec(name="dash", title="Dash", regions=[region])
        # AppSpec needs domain + workspaces minimum
        appspec = AppSpec(
            name="t",
            domain=DomainSpec(name="t", entities=[]),
            workspaces=[ws],
        )

        app = FastAPI()
        builder = WorkspaceRouteBuilder(
            app=app,
            appspec=appspec,
            entities=[],
            repositories={},
            auth_middleware=None,
            enable_auth=False,
            enable_test_mode=True,
        )
        builder.init_workspace_routes()
        paths = _route_paths(app)
        # The orphan region should NOT have a route — it's not in the
        # bodyless allowlist and has no source.
        assert "/api/workspaces/dash/regions/orphan" not in paths, (
            "Sourceless display: list should NOT get a route — only the "
            "four bodyless display modes are exempt from the source check"
        )
