"""Tests for workspace route generation, region wiring, and helpers.

Covers:
- Nav route generation (convert_shell_config)
- RegionContext filter_expr / action wiring (build_workspace_context)
- _parse_simple_where helper
- _AGGREGATE_RE regex
- Sort spec → repo format conversion
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Step 1 — Nav routes point to /workspaces/{name}
# ---------------------------------------------------------------------------


class TestNavRoutes:
    """convert_shell_config() should generate /workspaces/{name} routes."""

    def _make_workspace(self, name: str, label: str | None = None) -> Any:
        """Create a minimal WorkspaceSpec-like object."""
        return SimpleNamespace(name=name, label=label)

    def test_single_workspace_gets_workspace_route(self) -> None:
        from dazzle_ui.converters import convert_shell_config

        ws = [self._make_workspace("dashboard", "Dashboard")]
        shell = convert_shell_config(None, ws, "my_app")
        assert len(shell.nav.items) == 1
        assert shell.nav.items[0].route == "/workspaces/dashboard"

    def test_multiple_workspaces_all_get_workspace_routes(self) -> None:
        from dazzle_ui.converters import convert_shell_config

        ws = [
            self._make_workspace("overview"),
            self._make_workspace("settings"),
            self._make_workspace("admin_panel"),
        ]
        shell = convert_shell_config(None, ws, "my_app")
        routes = [item.route for item in shell.nav.items]
        assert routes == [
            "/workspaces/overview",
            "/workspaces/settings",
            "/workspaces/admin_panel",
        ]

    def test_first_workspace_no_longer_gets_root_slash(self) -> None:
        """Regression: first workspace used to get '/' — now it must not."""
        from dazzle_ui.converters import convert_shell_config

        ws = [self._make_workspace("main"), self._make_workspace("other")]
        shell = convert_shell_config(None, ws, "my_app")
        for item in shell.nav.items:
            assert item.route != "/"

    def test_workspace_label_fallback(self) -> None:
        from dazzle_ui.converters import convert_shell_config

        ws = [self._make_workspace("customer_dashboard")]
        shell = convert_shell_config(None, ws, "my_app")
        assert shell.nav.items[0].label == "Customer Dashboard"


# ---------------------------------------------------------------------------
# Step 2 — RegionContext wiring (filter_expr, action)
# ---------------------------------------------------------------------------


class TestRegionContextWiring:
    """build_workspace_context() should populate filter_expr and action fields."""

    def _make_condition(self) -> Any:
        """Create a ConditionExpr with a simple comparison."""
        from dazzle.core.ir.conditions import Comparison, ConditionExpr, ConditionValue

        return ConditionExpr(
            comparison=Comparison(
                field="status", operator="=", value=ConditionValue(literal="open")
            )
        )

    def _make_workspace_ir(
        self,
        *,
        filter_cond: Any = None,
        action: str | None = None,
        sort: list[Any] | None = None,
    ) -> Any:
        """Create a WorkspaceSpec IR object."""
        from dazzle.core.ir.workspaces import WorkspaceRegion, WorkspaceSpec

        region = WorkspaceRegion(
            name="test_region",
            source="Task",
            filter=filter_cond,
            action=action,
            sort=sort or [],
        )
        return WorkspaceSpec(
            name="test_ws",
            title="Test",
            regions=[region],
        )

    def _make_app_spec_with_surface(self, surface_name: str, entity_ref: str) -> Any:
        """Create minimal app_spec with one surface."""
        surface = SimpleNamespace(name=surface_name, entity_ref=entity_ref)
        return SimpleNamespace(surfaces=[surface])

    def test_filter_expr_populated_from_condition(self) -> None:
        import json

        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        cond = self._make_condition()
        ws = self._make_workspace_ir(filter_cond=cond)
        ctx = build_workspace_context(ws)

        assert ctx.regions[0].filter_expr != ""
        parsed = json.loads(ctx.regions[0].filter_expr)
        assert parsed["comparison"]["field"] == "status"
        assert parsed["comparison"]["operator"] == "="

    def test_filter_expr_empty_when_no_filter(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = self._make_workspace_ir()
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].filter_expr == ""

    def test_action_passed_through(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = self._make_workspace_ir(action="task_edit")
        app_spec = self._make_app_spec_with_surface("task_edit", "Task")
        ctx = build_workspace_context(ws, app_spec)

        assert ctx.regions[0].action == "task_edit"
        assert ctx.regions[0].action_url == "/tasks/{id}"

    def test_action_url_empty_when_no_surface_match(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = self._make_workspace_ir(action="nonexistent_surface")
        app_spec = self._make_app_spec_with_surface("other", "Other")
        ctx = build_workspace_context(ws, app_spec)

        assert ctx.regions[0].action == "nonexistent_surface"
        assert ctx.regions[0].action_url == ""

    def test_sort_specs_serialized(self) -> None:
        from dazzle.core.ir.ux import SortSpec
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = self._make_workspace_ir(sort=[SortSpec(field="due_date", direction="desc")])
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].sort == [{"field": "due_date", "direction": "desc"}]


# ---------------------------------------------------------------------------
# Step 3 — _parse_simple_where
# ---------------------------------------------------------------------------


class TestParseSimpleWhere:
    """_parse_simple_where() extracts filter dicts from WHERE strings."""

    def test_eq(self) -> None:
        from dazzle_back.runtime.server import _parse_simple_where

        result = _parse_simple_where("status = open")
        assert result == {"status": "open"}

    def test_ne(self) -> None:
        from dazzle_back.runtime.server import _parse_simple_where

        result = _parse_simple_where("status != complete")
        assert result == {"status__ne": "complete"}

    def test_and_conditions(self) -> None:
        from dazzle_back.runtime.server import _parse_simple_where

        result = _parse_simple_where("status != complete and status != cancelled")
        assert result == {"status__ne": "cancelled"}  # last wins for same field

    def test_gte(self) -> None:
        from dazzle_back.runtime.server import _parse_simple_where

        result = _parse_simple_where("priority >= high")
        assert result == {"priority__gte": "high"}

    def test_mixed_operators(self) -> None:
        from dazzle_back.runtime.server import _parse_simple_where

        result = _parse_simple_where("status = active and priority > 3")
        assert result == {"status": "active", "priority__gt": "3"}


# ---------------------------------------------------------------------------
# Step 3 — _AGGREGATE_RE
# ---------------------------------------------------------------------------


class TestAggregateRegex:
    """_AGGREGATE_RE parses aggregate expressions."""

    def test_bare_count(self) -> None:
        from dazzle_back.runtime.server import _AGGREGATE_RE

        m = _AGGREGATE_RE.match("count(Task)")
        assert m is not None
        assert m.group(1) == "count"
        assert m.group(2) == "Task"
        assert m.group(3) is None

    def test_count_with_where(self) -> None:
        from dazzle_back.runtime.server import _AGGREGATE_RE

        m = _AGGREGATE_RE.match("count(Task where status = open)")
        assert m is not None
        assert m.group(1) == "count"
        assert m.group(2) == "Task"
        assert m.group(3) == "status = open"

    def test_count_with_compound_where(self) -> None:
        from dazzle_back.runtime.server import _AGGREGATE_RE

        m = _AGGREGATE_RE.match("count(Invoice where status != paid and status != cancelled)")
        assert m is not None
        assert m.group(1) == "count"
        assert m.group(2) == "Invoice"
        assert "status != paid" in m.group(3)

    def test_sum(self) -> None:
        from dazzle_back.runtime.server import _AGGREGATE_RE

        m = _AGGREGATE_RE.match("sum(Invoice)")
        assert m is not None
        assert m.group(1) == "sum"
        assert m.group(2) == "Invoice"

    def test_no_match_on_bare_count(self) -> None:
        from dazzle_back.runtime.server import _AGGREGATE_RE

        m = _AGGREGATE_RE.match("count")
        assert m is None

    def test_spaces_around_parens(self) -> None:
        """DSL parser joins tokens with spaces — regex must tolerate this (#271)."""
        from dazzle_back.runtime.server import _AGGREGATE_RE

        m = _AGGREGATE_RE.match("count ( Task )")
        assert m is not None
        assert m.group(1) == "count"
        assert m.group(2) == "Task"

    def test_spaces_in_where_clause(self) -> None:
        from dazzle_back.runtime.server import _AGGREGATE_RE

        m = _AGGREGATE_RE.match("count ( Task where status = open )")
        assert m is not None
        assert m.group(1) == "count"
        assert m.group(2) == "Task"
        assert m.group(3).strip() == "status = open"

    def test_leading_spaces(self) -> None:
        from dazzle_back.runtime.server import _AGGREGATE_RE

        m = _AGGREGATE_RE.match("  count(Task)")
        assert m is not None
        assert m.group(2) == "Task"


# ---------------------------------------------------------------------------
# Sort spec → repo format
# ---------------------------------------------------------------------------


class TestSortSpecConversion:
    """SortSpec list should convert to repo-friendly string list."""

    def test_asc_sort(self) -> None:
        from dazzle.core.ir.ux import SortSpec

        specs = [SortSpec(field="name", direction="asc")]
        result = [s.field if s.direction == "asc" else f"-{s.field}" for s in specs]
        assert result == ["name"]

    def test_desc_sort(self) -> None:
        from dazzle.core.ir.ux import SortSpec

        specs = [SortSpec(field="due_date", direction="desc")]
        result = [s.field if s.direction == "asc" else f"-{s.field}" for s in specs]
        assert result == ["-due_date"]

    def test_mixed_sort(self) -> None:
        from dazzle.core.ir.ux import SortSpec

        specs = [
            SortSpec(field="status", direction="asc"),
            SortSpec(field="created_at", direction="desc"),
        ]
        result = [s.field if s.direction == "asc" else f"-{s.field}" for s in specs]
        assert result == ["status", "-created_at"]


# ---------------------------------------------------------------------------
# Step 5 — Workspace routes enforce auth (#145)
# ---------------------------------------------------------------------------

try:
    import fastapi  # noqa: F401

    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False


@pytest.mark.skipif(not _FASTAPI_AVAILABLE, reason="FastAPI required")
class TestWorkspaceAuthEnforcement:
    """Workspace page routes must require authentication when auth is enabled."""

    def _make_spec(self) -> Any:
        """Build a BackendSpec with one workspace."""
        from dazzle.core.ir.workspaces import WorkspaceRegion, WorkspaceSpec
        from dazzle_back.specs import BackendSpec, EntitySpec, FieldSpec, FieldType, ScalarType

        return BackendSpec(
            name="test_app",
            version="1.0.0",
            entities=[
                EntitySpec(
                    name="Task",
                    fields=[
                        FieldSpec(
                            name="id",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                            required=True,
                        ),
                        FieldSpec(
                            name="title",
                            type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                            required=True,
                        ),
                    ],
                ),
            ],
            workspaces=[
                WorkspaceSpec(
                    name="admin_dashboard",
                    title="Admin Dashboard",
                    regions=[
                        WorkspaceRegion(name="tasks", source="Task"),
                    ],
                ),
            ],
        )

    @pytest.fixture
    def app_with_auth(self, tmp_path: Any) -> Any:
        """Build a FastAPI app with auth enabled and one workspace."""
        from unittest.mock import patch

        from dazzle_back.runtime.server import DazzleBackendApp, ServerConfig

        config = ServerConfig(
            database_url="postgresql://mock/test",
            enable_auth=True,
            enable_test_mode=False,
        )
        with (
            patch("dazzle_back.runtime.pg_backend.PostgresBackend"),
            patch("dazzle_back.runtime.server.auto_migrate"),
            patch("dazzle_back.runtime.auth.AuthStore._init_db"),
        ):
            builder = DazzleBackendApp(self._make_spec(), config=config)
            return builder.build()

    @pytest.fixture
    def app_without_auth(self, tmp_path: Any) -> Any:
        """Build a FastAPI app with auth disabled and one workspace."""
        from unittest.mock import patch

        from dazzle_back.runtime.server import DazzleBackendApp, ServerConfig

        config = ServerConfig(
            database_url="postgresql://mock/test",
            enable_auth=False,
            enable_test_mode=False,
        )
        with (
            patch("dazzle_back.runtime.pg_backend.PostgresBackend"),
            patch("dazzle_back.runtime.server.auto_migrate"),
        ):
            builder = DazzleBackendApp(self._make_spec(), config=config)
            return builder.build()

    def test_workspace_html_route_not_on_root(self, app_with_auth: Any) -> None:
        """Root-level /workspaces/{name} HTML route is no longer registered.

        Workspace HTML pages are served by page_routes.py at /app/workspaces/{name}
        in the unified server. The backend app only exposes region API endpoints.
        """
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth, raise_server_exceptions=False)
        resp = client.get("/workspaces/admin_dashboard")
        assert resp.status_code == 404

    def test_workspace_region_returns_401_without_session(self, app_with_auth: Any) -> None:
        """Workspace region data returns 401 when auth is enabled and no session cookie."""
        from fastapi.testclient import TestClient

        client = TestClient(app_with_auth, raise_server_exceptions=False)
        resp = client.get("/api/workspaces/admin_dashboard/regions/tasks")
        assert resp.status_code == 401

    def test_workspace_accessible_without_auth_when_disabled(self, app_without_auth: Any) -> None:
        """Workspace region data accessible when auth is disabled."""
        from fastapi.testclient import TestClient

        client = TestClient(app_without_auth, raise_server_exceptions=False)
        resp = client.get("/api/workspaces/admin_dashboard/regions/tasks")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Step 6 — Workspace list template handles ref columns (#272)
# ---------------------------------------------------------------------------

try:
    from dazzle_ui.runtime.template_renderer import render_fragment

    HAS_TEMPLATE_RENDERER = True
except ImportError:
    HAS_TEMPLATE_RENDERER = False


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestWorkspaceListRefColumn:
    """Workspace list template renders ref columns with resolved display names."""

    def test_ref_column_shows_name(self) -> None:
        html = render_fragment(
            "workspace/regions/list.html",
            title="Tasks",
            columns=[
                {"key": "title", "label": "Title", "type": "text", "sortable": True},
                {"key": "assigned_to", "label": "Assigned To", "type": "ref", "sortable": False},
            ],
            items=[
                {"id": "1", "title": "Fix bug", "assigned_to": {"id": "u1", "name": "Alice"}},
                {"id": "2", "title": "Review PR", "assigned_to": None},
            ],
            endpoint="/api/workspaces/ws/regions/tasks",
            region_name="tasks",
            total=2,
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            action_url="",
            empty_message="No tasks.",
        )
        assert "Alice" in html
        assert "-" in html  # None ref shows dash

    def test_ref_column_uses_title_fallback(self) -> None:
        html = render_fragment(
            "workspace/regions/list.html",
            title="Items",
            columns=[
                {"key": "company", "label": "Company", "type": "ref", "sortable": False},
            ],
            items=[
                {"id": "1", "company": {"id": "c1", "title": "Acme Corp"}},
            ],
            endpoint="/api/workspaces/ws/regions/items",
            region_name="items",
            total=1,
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            action_url="",
            empty_message="No items.",
        )
        assert "Acme Corp" in html


# ---------------------------------------------------------------------------
# Step 7 — SSE connection is conditional (#273)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestWorkspaceSSEConditional:
    """SSE attributes in _content.html must only appear when sse_url is set."""

    def _make_workspace_ctx(self, sse_url: str = "") -> Any:
        from dazzle_ui.runtime.workspace_renderer import RegionContext, WorkspaceContext

        return WorkspaceContext(
            name="dashboard",
            title="Dashboard",
            sse_url=sse_url,
            regions=[
                RegionContext(
                    name="tasks",
                    title="Tasks",
                    source="Task",
                    endpoint="/api/workspaces/dashboard/regions/tasks",
                ),
            ],
        )

    def test_no_sse_attributes_when_sse_url_empty(self) -> None:
        ws = self._make_workspace_ctx(sse_url="")
        html = render_fragment("workspace/_content.html", workspace=ws)
        assert "sse-connect" not in html
        assert 'hx-ext="sse"' not in html
        assert "sse:entity.created" not in html

    def test_sse_attributes_present_when_sse_url_set(self) -> None:
        ws = self._make_workspace_ctx(sse_url="/_ops/sse/events")
        html = render_fragment("workspace/_content.html", workspace=ws)
        assert 'sse-connect="/_ops/sse/events"' in html
        assert 'hx-ext="sse"' in html
        assert "sse:entity.created" in html

    def test_regions_still_load_without_sse(self) -> None:
        """Regions should still have hx-get and load trigger even without SSE."""
        ws = self._make_workspace_ctx(sse_url="")
        html = render_fragment("workspace/_content.html", workspace=ws)
        assert "hx-get=" in html
        assert 'hx-trigger="load"' in html
