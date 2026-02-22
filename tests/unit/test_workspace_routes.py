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
        domain = SimpleNamespace(entities=[])
        return SimpleNamespace(surfaces=[surface], domain=domain)

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
        """Build an AppSpec with one workspace."""
        from dazzle.core.ir.appspec import AppSpec
        from dazzle.core.ir.domain import DomainSpec
        from dazzle.core.ir.domain import EntitySpec as IREntitySpec
        from dazzle.core.ir.fields import FieldSpec as IRFieldSpec
        from dazzle.core.ir.fields import FieldType as IRFieldType
        from dazzle.core.ir.fields import FieldTypeKind
        from dazzle.core.ir.workspaces import WorkspaceRegion, WorkspaceSpec

        return AppSpec(
            name="test_app",
            version="1.0.0",
            domain=DomainSpec(
                entities=[
                    IREntitySpec(
                        name="Task",
                        title="Task",
                        fields=[
                            IRFieldSpec(
                                name="id",
                                type=IRFieldType(kind=FieldTypeKind.UUID),
                                modifiers=["pk"],
                            ),
                            IRFieldSpec(
                                name="title",
                                type=IRFieldType(kind=FieldTypeKind.STR, max_length=200),
                                modifiers=["required"],
                            ),
                        ],
                    ),
                ]
            ),
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
class TestWorkspaceRefLinks:
    """Workspace templates render ref columns as clickable links (#285)."""

    def test_list_ref_link_rendered(self) -> None:
        """List template renders ref column with ref_route as a clickable link."""
        html = render_fragment(
            "workspace/regions/list.html",
            title="Tasks",
            columns=[
                {"key": "title", "label": "Title", "type": "text", "sortable": True},
                {
                    "key": "assigned_to",
                    "label": "Assigned To",
                    "type": "ref",
                    "sortable": False,
                    "ref_route": "/users/{id}",
                },
            ],
            items=[
                {
                    "id": "t1",
                    "title": "Fix bug",
                    "assigned_to": {"id": "u1", "name": "Alice"},
                },
            ],
            endpoint="/api/workspaces/ws/regions/tasks",
            region_name="tasks",
            total=1,
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            action_url="",
            empty_message="No tasks.",
        )
        assert "Alice" in html
        assert "/users/u1" in html
        assert "link-primary" in html

    def test_list_ref_no_link_without_ref_route(self) -> None:
        """Ref column without ref_route renders display name without link."""
        html = render_fragment(
            "workspace/regions/list.html",
            title="Tasks",
            columns=[
                {
                    "key": "owner",
                    "label": "Owner",
                    "type": "ref",
                    "sortable": False,
                },
            ],
            items=[
                {"id": "t1", "owner": {"id": "u1", "name": "Bob"}},
            ],
            endpoint="/api/workspaces/ws/regions/tasks",
            region_name="tasks",
            total=1,
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            action_url="",
            empty_message="No tasks.",
        )
        assert "Bob" in html
        assert "<a " not in html or "/users/" not in html

    def test_detail_ref_link_rendered(self) -> None:
        """Detail template renders ref column with clickable link."""
        html = render_fragment(
            "workspace/regions/detail.html",
            title="Task Detail",
            columns=[
                {
                    "key": "company",
                    "label": "Company",
                    "type": "ref",
                    "sortable": False,
                    "ref_route": "/companies/{id}",
                },
            ],
            item={"id": "t1", "company": {"id": "c1", "name": "Acme Corp"}},
            empty_message="No record.",
        )
        assert "Acme Corp" in html
        assert "/companies/c1" in html

    def test_ref_link_with_uuid_id(self) -> None:
        """Ref link works with UUID-style IDs."""
        from uuid import uuid4

        uid = str(uuid4())
        html = render_fragment(
            "workspace/regions/list.html",
            title="Tasks",
            columns=[
                {
                    "key": "owner",
                    "label": "Owner",
                    "type": "ref",
                    "sortable": False,
                    "ref_route": "/users/{id}",
                },
            ],
            items=[
                {"id": "t1", "owner": {"id": uid, "name": "Charlie"}},
            ],
            endpoint="/api/workspaces/ws/regions/tasks",
            region_name="tasks",
            total=1,
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            action_url="",
            empty_message="No tasks.",
        )
        assert "Charlie" in html
        assert f"/users/{uid}" in html

    def test_ref_null_value_shows_dash(self) -> None:
        """Null ref value shows dash, not error."""
        html = render_fragment(
            "workspace/regions/list.html",
            title="Tasks",
            columns=[
                {
                    "key": "owner",
                    "label": "Owner",
                    "type": "ref",
                    "sortable": False,
                    "ref_route": "/users/{id}",
                },
            ],
            items=[
                {"id": "t1", "owner": None},
            ],
            endpoint="/api/workspaces/ws/regions/tasks",
            region_name="tasks",
            total=1,
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            action_url="",
            empty_message="No tasks.",
        )
        assert "-" in html


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


# ---------------------------------------------------------------------------
# Step 8 — Kanban display mode (#274)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestKanbanTemplate:
    """Kanban template renders items grouped into columns by a field."""

    def test_kanban_renders_columns(self) -> None:
        html = render_fragment(
            "workspace/regions/kanban.html",
            title="Tasks",
            columns=[
                {"key": "title", "label": "Title", "type": "text", "sortable": True},
                {"key": "status", "label": "Status", "type": "badge", "sortable": False},
            ],
            items=[
                {"id": "1", "title": "Fix bug", "status": "todo"},
                {"id": "2", "title": "Write docs", "status": "in_progress"},
                {"id": "3", "title": "Ship it", "status": "todo"},
            ],
            kanban_columns=["todo", "in_progress", "done"],
            group_by="status",
            display_key="title",
            total=3,
            action_url="",
            empty_message="No tasks.",
            endpoint="/api/workspaces/ws/regions/tasks",
            region_name="tasks",
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            metrics=[],
        )
        # Verify column headers are rendered
        assert "todo" in html
        assert "in_progress" in html
        assert "done" in html
        # Verify items are present
        assert "Fix bug" in html
        assert "Write docs" in html
        assert "Ship it" in html

    def test_kanban_empty_column_shows_placeholder(self) -> None:
        html = render_fragment(
            "workspace/regions/kanban.html",
            title="Tasks",
            columns=[
                {"key": "title", "label": "Title", "type": "text", "sortable": True},
            ],
            items=[
                {"id": "1", "title": "Fix bug", "status": "todo"},
            ],
            kanban_columns=["todo", "done"],
            group_by="status",
            display_key="title",
            total=1,
            action_url="",
            empty_message="No tasks.",
            endpoint="/api/workspaces/ws/regions/tasks",
            region_name="tasks",
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            metrics=[],
        )
        # "done" column should show empty placeholder
        assert "No items" in html

    def test_kanban_with_action_url(self) -> None:
        html = render_fragment(
            "workspace/regions/kanban.html",
            title="Tasks",
            columns=[
                {"key": "title", "label": "Title", "type": "text", "sortable": True},
            ],
            items=[
                {"id": "abc-123", "title": "Fix bug", "status": "todo"},
            ],
            kanban_columns=["todo"],
            group_by="status",
            display_key="title",
            total=1,
            action_url="/tasks/{id}",
            empty_message="No tasks.",
            endpoint="/api/workspaces/ws/regions/tasks",
            region_name="tasks",
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            metrics=[],
        )
        assert "/tasks/abc-123" in html
        assert "hx-get" in html

    def test_kanban_ref_column_resolved(self) -> None:
        html = render_fragment(
            "workspace/regions/kanban.html",
            title="Tasks",
            columns=[
                {"key": "title", "label": "Title", "type": "text", "sortable": True},
                {"key": "assigned_to", "label": "Assigned", "type": "ref", "sortable": False},
            ],
            items=[
                {
                    "id": "1",
                    "title": "Review PR",
                    "status": "todo",
                    "assigned_to": {"id": "u1", "name": "Alice"},
                },
            ],
            kanban_columns=["todo"],
            group_by="status",
            display_key="title",
            total=1,
            action_url="",
            empty_message="No tasks.",
            endpoint="/api/workspaces/ws/regions/tasks",
            region_name="tasks",
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            metrics=[],
        )
        assert "Alice" in html

    def test_kanban_load_all_button_when_truncated(self) -> None:
        html = render_fragment(
            "workspace/regions/kanban.html",
            title="Tasks",
            columns=[
                {"key": "title", "label": "Title", "type": "text", "sortable": True},
            ],
            items=[
                {"id": "1", "title": "Task 1", "status": "todo"},
                {"id": "2", "title": "Task 2", "status": "todo"},
            ],
            kanban_columns=["todo"],
            group_by="status",
            display_key="title",
            total=100,
            action_url="",
            empty_message="No tasks.",
            endpoint="/api/workspaces/ws/regions/tasks",
            region_name="tasks",
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            metrics=[],
        )
        assert "Showing 2 of 100" in html
        assert "Load all" in html
        assert "page_size=100" in html

    def test_kanban_no_load_all_when_all_shown(self) -> None:
        html = render_fragment(
            "workspace/regions/kanban.html",
            title="Tasks",
            columns=[
                {"key": "title", "label": "Title", "type": "text", "sortable": True},
            ],
            items=[
                {"id": "1", "title": "Task 1", "status": "todo"},
            ],
            kanban_columns=["todo"],
            group_by="status",
            display_key="title",
            total=1,
            action_url="",
            empty_message="No tasks.",
            endpoint="/api/workspaces/ws/regions/tasks",
            region_name="tasks",
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            metrics=[],
        )
        assert "Load all" not in html
        assert "Showing" not in html

    def test_kanban_no_items(self) -> None:
        html = render_fragment(
            "workspace/regions/kanban.html",
            title="Tasks",
            columns=[],
            items=[],
            kanban_columns=[],
            group_by="status",
            display_key="title",
            total=0,
            action_url="",
            empty_message="No tasks yet.",
            endpoint="/api/workspaces/ws/regions/tasks",
            region_name="tasks",
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            metrics=[],
        )
        assert "No tasks yet." in html


class TestKanbanTemplateMapping:
    """KANBAN display mode maps to kanban.html template."""

    def test_kanban_in_display_template_map(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert "KANBAN" in DISPLAY_TEMPLATE_MAP
        assert DISPLAY_TEMPLATE_MAP["KANBAN"] == "workspace/regions/kanban.html"

    def test_build_workspace_context_selects_kanban_template(self) -> None:
        from dazzle.core.ir.workspaces import WorkspaceRegion, WorkspaceSpec
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = WorkspaceSpec(
            name="board",
            title="Task Board",
            regions=[
                WorkspaceRegion(
                    name="tasks_by_status",
                    source="Task",
                    display="kanban",
                    group_by="status",
                ),
            ],
        )
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].template == "workspace/regions/kanban.html"
        assert ctx.regions[0].display == "KANBAN"
        assert ctx.regions[0].group_by == "status"


# ---------------------------------------------------------------------------
# Step 9 — Timeline display mode (#274)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestTimelineTemplate:
    """Timeline template renders items as a vertical timeline."""

    def test_timeline_renders_items(self) -> None:
        html = render_fragment(
            "workspace/regions/timeline.html",
            title="Audit Log",
            columns=[
                {"key": "action", "label": "Action", "type": "text", "sortable": True},
                {"key": "status", "label": "Status", "type": "badge", "sortable": False},
                {"key": "created_at", "label": "When", "type": "date", "sortable": True},
            ],
            items=[
                {
                    "id": "1",
                    "action": "Created company",
                    "status": "complete",
                    "created_at": "2026-01-15T10:30:00",
                },
                {
                    "id": "2",
                    "action": "Started CDD",
                    "status": "in_progress",
                    "created_at": "2026-01-15T10:35:00",
                },
            ],
            display_key="action",
            total=2,
            action_url="",
            empty_message="No events.",
            endpoint="/api/workspaces/ws/regions/log",
            region_name="log",
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            metrics=[],
        )
        assert "Created company" in html
        assert "Started CDD" in html
        assert "timeline" in html

    def test_timeline_empty(self) -> None:
        html = render_fragment(
            "workspace/regions/timeline.html",
            title="Events",
            columns=[],
            items=[],
            display_key="action",
            total=0,
            action_url="",
            empty_message="Nothing happened yet.",
            endpoint="/api/workspaces/ws/regions/events",
            region_name="events",
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            metrics=[],
        )
        assert "Nothing happened yet." in html

    def test_timeline_in_display_template_map(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert "TIMELINE" in DISPLAY_TEMPLATE_MAP
        assert DISPLAY_TEMPLATE_MAP["TIMELINE"] == "workspace/regions/timeline.html"

    def test_build_workspace_context_selects_timeline_template(self) -> None:
        from dazzle.core.ir.workspaces import WorkspaceRegion, WorkspaceSpec
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = WorkspaceSpec(
            name="history",
            title="History",
            regions=[
                WorkspaceRegion(
                    name="audit_log",
                    source="AuditLog",
                    display="timeline",
                ),
            ],
        )
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].template == "workspace/regions/timeline.html"
        assert ctx.regions[0].display == "TIMELINE"


# ---------------------------------------------------------------------------
# Step 10 — Bar chart and funnel chart display modes (#274)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestBarChartTemplate:
    """Bar chart template renders items grouped by a field as horizontal bars."""

    def test_bar_chart_renders_bars(self) -> None:
        html = render_fragment(
            "workspace/regions/bar_chart.html",
            title="Tasks by Status",
            columns=[],
            items=[
                {"id": "1", "status": "todo"},
                {"id": "2", "status": "todo"},
                {"id": "3", "status": "in_progress"},
                {"id": "4", "status": "done"},
            ],
            group_by="status",
            kanban_columns=[],
            display_key="id",
            total=4,
            action_url="",
            empty_message="No tasks.",
            endpoint="/api/workspaces/ws/regions/tasks",
            region_name="tasks",
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            metrics=[],
        )
        assert "todo" in html
        assert "in_progress" in html
        assert "done" in html
        assert "4 total" in html

    def test_bar_chart_metrics_fallback(self) -> None:
        html = render_fragment(
            "workspace/regions/bar_chart.html",
            title="Overview",
            columns=[],
            items=[],
            group_by="",
            kanban_columns=[],
            display_key="id",
            total=0,
            action_url="",
            empty_message="No data.",
            endpoint="/api/workspaces/ws/regions/overview",
            region_name="overview",
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            metrics=[
                {"label": "Open Tasks", "value": 12},
                {"label": "Closed Tasks", "value": 8},
            ],
        )
        assert "Open Tasks" in html
        assert "Closed Tasks" in html

    def test_bar_chart_empty(self) -> None:
        html = render_fragment(
            "workspace/regions/bar_chart.html",
            title="Empty",
            columns=[],
            items=[],
            group_by="",
            kanban_columns=[],
            display_key="id",
            total=0,
            action_url="",
            empty_message="Nothing here.",
            endpoint="/api/workspaces/ws/regions/empty",
            region_name="empty",
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            metrics=[],
        )
        assert "Nothing here." in html

    def test_bar_chart_in_template_map(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert "BAR_CHART" in DISPLAY_TEMPLATE_MAP


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestFunnelChartTemplate:
    """Funnel chart template renders ordered stages as narrowing bars."""

    def test_funnel_renders_stages(self) -> None:
        html = render_fragment(
            "workspace/regions/funnel_chart.html",
            title="Onboarding Pipeline",
            columns=[],
            items=[
                {"id": "1", "stage": "started"},
                {"id": "2", "stage": "started"},
                {"id": "3", "stage": "started"},
                {"id": "4", "stage": "basics"},
                {"id": "5", "stage": "basics"},
                {"id": "6", "stage": "complete"},
            ],
            kanban_columns=["started", "basics", "complete"],
            group_by="stage",
            display_key="id",
            total=6,
            action_url="",
            empty_message="No data.",
            endpoint="/api/workspaces/ws/regions/pipeline",
            region_name="pipeline",
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            metrics=[],
        )
        assert "started" in html
        assert "basics" in html
        assert "complete" in html
        assert "(3)" in html  # 3 in started
        assert "(1)" in html  # 1 in complete

    def test_funnel_empty(self) -> None:
        html = render_fragment(
            "workspace/regions/funnel_chart.html",
            title="Empty Funnel",
            columns=[],
            items=[],
            kanban_columns=[],
            group_by="stage",
            display_key="id",
            total=0,
            action_url="",
            empty_message="No pipeline data.",
            endpoint="/api/workspaces/ws/regions/funnel",
            region_name="funnel",
            sort_field="",
            sort_dir="asc",
            filter_columns=[],
            active_filters={},
            metrics=[],
        )
        assert "No pipeline data." in html

    def test_funnel_in_template_map(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert "FUNNEL_CHART" in DISPLAY_TEMPLATE_MAP


# ---------------------------------------------------------------------------
# Step 11 — Template constant folding: pre-computed columns (#282)
# ---------------------------------------------------------------------------


class TestBuildEntityColumns:
    """_build_entity_columns() pre-computes column metadata from entity spec."""

    def test_basic_columns(self) -> None:
        from dazzle_back.runtime.server import _build_entity_columns

        entity = SimpleNamespace(
            fields=[
                SimpleNamespace(
                    name="id", type=SimpleNamespace(kind=SimpleNamespace(value="uuid"))
                ),
                SimpleNamespace(
                    name="title",
                    label=None,
                    type=SimpleNamespace(kind=SimpleNamespace(value="str")),
                ),
                SimpleNamespace(
                    name="completed",
                    label="Done",
                    type=SimpleNamespace(kind=SimpleNamespace(value="bool")),
                ),
            ],
            state_machine=None,
        )
        cols = _build_entity_columns(entity)
        assert len(cols) == 2  # id is skipped
        assert cols[0]["key"] == "title"
        assert cols[0]["type"] == "text"
        assert cols[0]["sortable"] is True
        assert cols[1]["key"] == "completed"
        assert cols[1]["type"] == "bool"
        assert cols[1]["filterable"] is True
        assert cols[1]["filter_options"] == ["true", "false"]

    def test_enum_column_has_filter_options(self) -> None:
        from dazzle_back.runtime.server import _build_entity_columns

        entity = SimpleNamespace(
            fields=[
                SimpleNamespace(
                    name="id", type=SimpleNamespace(kind=SimpleNamespace(value="uuid"))
                ),
                SimpleNamespace(
                    name="priority",
                    label="Priority",
                    type=SimpleNamespace(
                        kind=SimpleNamespace(value="enum"),
                        enum_values=["low", "medium", "high"],
                    ),
                ),
            ],
            state_machine=None,
        )
        cols = _build_entity_columns(entity)
        assert len(cols) == 1
        assert cols[0]["type"] == "badge"
        assert cols[0]["filterable"] is True
        assert cols[0]["filter_options"] == ["low", "medium", "high"]

    def test_ref_column(self) -> None:
        from dazzle_back.runtime.server import _build_entity_columns

        entity = SimpleNamespace(
            fields=[
                SimpleNamespace(
                    name="id", type=SimpleNamespace(kind=SimpleNamespace(value="uuid"))
                ),
                SimpleNamespace(
                    name="project_id",
                    label="Project",
                    type=SimpleNamespace(kind=SimpleNamespace(value="ref")),
                ),
            ],
            state_machine=None,
        )
        cols = _build_entity_columns(entity)
        assert len(cols) == 1
        assert cols[0]["key"] == "project"
        assert cols[0]["type"] == "ref"
        assert cols[0]["sortable"] is False

    def test_ref_column_with_ref_entity(self) -> None:
        """ref_route should be a plain string with the entity's API plural."""
        from dazzle_back.runtime.server import _build_entity_columns

        entity = SimpleNamespace(
            fields=[
                SimpleNamespace(
                    name="id", type=SimpleNamespace(kind=SimpleNamespace(value="uuid"))
                ),
                SimpleNamespace(
                    name="assigned_to_id",
                    label="Assigned To",
                    type=SimpleNamespace(kind=SimpleNamespace(value="ref"), ref_entity="User"),
                ),
            ],
            state_machine=None,
        )
        cols = _build_entity_columns(entity)
        assert len(cols) == 1
        assert cols[0]["key"] == "assigned_to"
        assert cols[0]["ref_route"] == "/users/{id}"
        # Ensure ref_route is a plain string (no pydantic/Cython objects)
        assert type(cols[0]["ref_route"]) is str

    def test_ref_column_without_ref_entity(self) -> None:
        """ref_route should be empty when ref_entity is not set."""
        from dazzle_back.runtime.server import _build_entity_columns

        entity = SimpleNamespace(
            fields=[
                SimpleNamespace(
                    name="id", type=SimpleNamespace(kind=SimpleNamespace(value="uuid"))
                ),
                SimpleNamespace(
                    name="owner_id",
                    label=None,
                    type=SimpleNamespace(kind=SimpleNamespace(value="ref"), ref_entity=None),
                ),
            ],
            state_machine=None,
        )
        cols = _build_entity_columns(entity)
        assert len(cols) == 1
        assert cols[0]["ref_route"] == ""

    def test_state_machine_column(self) -> None:
        from dazzle_back.runtime.server import _build_entity_columns

        entity = SimpleNamespace(
            fields=[
                SimpleNamespace(
                    name="id", type=SimpleNamespace(kind=SimpleNamespace(value="uuid"))
                ),
                SimpleNamespace(
                    name="status",
                    label=None,
                    type=SimpleNamespace(kind=SimpleNamespace(value="str")),
                ),
            ],
            state_machine=SimpleNamespace(
                status_field="status",
                states=["draft", "active", "closed"],
            ),
        )
        cols = _build_entity_columns(entity)
        assert len(cols) == 1
        assert cols[0]["type"] == "badge"
        assert cols[0]["filterable"] is True
        assert cols[0]["filter_options"] == ["draft", "active", "closed"]

    def test_money_column(self) -> None:
        from dazzle_back.runtime.server import _build_entity_columns

        entity = SimpleNamespace(
            fields=[
                SimpleNamespace(
                    name="id", type=SimpleNamespace(kind=SimpleNamespace(value="uuid"))
                ),
                SimpleNamespace(
                    name="amount",
                    label="Amount",
                    type=SimpleNamespace(kind=SimpleNamespace(value="money"), currency_code="USD"),
                ),
            ],
            state_machine=None,
        )
        cols = _build_entity_columns(entity)
        assert len(cols) == 1
        assert cols[0]["key"] == "amount_minor"
        assert cols[0]["type"] == "currency"
        assert cols[0]["currency_code"] == "USD"

    def test_max_8_columns(self) -> None:
        from dazzle_back.runtime.server import _build_entity_columns

        fields = [
            SimpleNamespace(name="id", type=SimpleNamespace(kind=SimpleNamespace(value="uuid")))
        ]
        for i in range(12):
            fields.append(
                SimpleNamespace(
                    name=f"field_{i}",
                    label=None,
                    type=SimpleNamespace(kind=SimpleNamespace(value="str")),
                )
            )
        entity = SimpleNamespace(fields=fields, state_machine=None)
        cols = _build_entity_columns(entity)
        assert len(cols) == 8

    def test_none_entity_returns_empty(self) -> None:
        from dazzle_back.runtime.server import _build_entity_columns

        assert _build_entity_columns(None) == []

    def test_hidden_relation_types(self) -> None:
        from dazzle_back.runtime.server import _build_entity_columns

        entity = SimpleNamespace(
            fields=[
                SimpleNamespace(
                    name="id", type=SimpleNamespace(kind=SimpleNamespace(value="uuid"))
                ),
                SimpleNamespace(
                    name="items",
                    label=None,
                    type=SimpleNamespace(kind=SimpleNamespace(value="has_many")),
                ),
                SimpleNamespace(
                    name="parent",
                    label=None,
                    type=SimpleNamespace(kind=SimpleNamespace(value="belongs_to")),
                ),
                SimpleNamespace(
                    name="title",
                    label=None,
                    type=SimpleNamespace(kind=SimpleNamespace(value="str")),
                ),
            ],
            state_machine=None,
        )
        cols = _build_entity_columns(entity)
        assert len(cols) == 1
        assert cols[0]["key"] == "title"


# ---------------------------------------------------------------------------
# Step 12 — Aggregate metric batching (#283)
# ---------------------------------------------------------------------------


class TestComputeAggregateMetrics:
    """_compute_aggregate_metrics batches independent DB queries concurrently."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_fastapi(self) -> None:
        pytest.importorskip("fastapi")

    @pytest.mark.asyncio
    async def test_count_metrics_batched_concurrently(self) -> None:
        """Multiple count() aggregates should run concurrently via gather."""
        import asyncio

        from dazzle_back.runtime.server import _compute_aggregate_metrics

        call_order: list[str] = []

        class MockRepo:
            def __init__(self, name: str, total: int) -> None:
                self.name = name
                self.total = total

            async def list(self, **kwargs: Any) -> dict[str, Any]:
                call_order.append(f"start_{self.name}")
                await asyncio.sleep(0.01)
                call_order.append(f"end_{self.name}")
                return {"items": [], "total": self.total}

        repos = {
            "Task": MockRepo("Task", 42),
            "Invoice": MockRepo("Invoice", 7),
        }
        aggregates = {
            "open_tasks": "count(Task where status = open)",
            "unpaid_invoices": "count(Invoice where status != paid)",
        }

        metrics = await _compute_aggregate_metrics(aggregates, repos, 0, [])

        assert len(metrics) == 2
        assert metrics[0]["label"] == "Open Tasks"
        assert metrics[0]["value"] == 42
        assert metrics[1]["label"] == "Unpaid Invoices"
        assert metrics[1]["value"] == 7

        # Verify concurrent execution: both should start before either ends
        assert call_order[0].startswith("start_")
        assert call_order[1].startswith("start_")

    @pytest.mark.asyncio
    async def test_sync_metrics_not_batched(self) -> None:
        """Legacy 'count' and 'sum:field' metrics compute synchronously."""
        from dazzle_back.runtime.server import _compute_aggregate_metrics

        items = [
            {"amount": 100},
            {"amount": 200},
            {"amount": 50},
        ]
        aggregates = {
            "total_items": "count",
            "total_amount": "sum:amount",
        }

        metrics = await _compute_aggregate_metrics(aggregates, None, 99, items)

        assert len(metrics) == 2
        assert metrics[0]["value"] == 99  # Legacy count uses total
        assert metrics[1]["value"] == 350.0  # Sum of amounts

    @pytest.mark.asyncio
    async def test_mixed_sync_and_async_metrics(self) -> None:
        """Mix of count(), legacy count, and sum: metrics."""
        from dazzle_back.runtime.server import _compute_aggregate_metrics

        class MockRepo:
            async def list(self, **kwargs: Any) -> dict[str, Any]:
                return {"items": [], "total": 15}

        repos = {"Task": MockRepo()}
        items = [{"value": 10}, {"value": 20}]
        aggregates = {
            "db_count": "count(Task)",
            "legacy_count": "count",
            "field_sum": "sum:value",
        }

        metrics = await _compute_aggregate_metrics(aggregates, repos, 50, items)

        assert len(metrics) == 3
        assert metrics[0]["value"] == 15  # DB count
        assert metrics[1]["value"] == 50  # Legacy total
        assert metrics[2]["value"] == 30.0  # Sum

    @pytest.mark.asyncio
    async def test_order_preserved(self) -> None:
        """Metrics should be returned in the same order as aggregates dict."""
        from dazzle_back.runtime.server import _compute_aggregate_metrics

        aggregates = {
            "alpha": "count",
            "beta": "count",
            "gamma": "count",
        }

        metrics = await _compute_aggregate_metrics(aggregates, None, 10, [])

        assert [m["label"] for m in metrics] == ["Alpha", "Beta", "Gamma"]

    @pytest.mark.asyncio
    async def test_db_error_returns_zero(self) -> None:
        """A failing DB query should return 0 for that metric, not crash."""
        from dazzle_back.runtime.server import _compute_aggregate_metrics

        class FailingRepo:
            async def list(self, **kwargs: Any) -> dict[str, Any]:
                raise RuntimeError("DB connection lost")

        repos = {"Task": FailingRepo()}
        aggregates = {"broken": "count(Task)"}

        metrics = await _compute_aggregate_metrics(aggregates, repos, 0, [])

        assert len(metrics) == 1
        assert metrics[0]["value"] == 0

    @pytest.mark.asyncio
    async def test_empty_aggregates(self) -> None:
        """Empty aggregates dict returns empty list."""
        from dazzle_back.runtime.server import _compute_aggregate_metrics

        metrics = await _compute_aggregate_metrics({}, None, 0, [])
        assert metrics == []


# ---------------------------------------------------------------------------
# Step 12 — Workspace batch endpoint (#283)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _FASTAPI_AVAILABLE, reason="FastAPI required")
class TestWorkspaceBatchEndpoint:
    """Batch endpoint fetches all regions concurrently."""

    def _make_spec_with_aggregates(self) -> Any:
        """Build an AppSpec with a workspace that has multiple regions."""
        from dazzle.core.ir.appspec import AppSpec
        from dazzle.core.ir.domain import DomainSpec
        from dazzle.core.ir.domain import EntitySpec as IREntitySpec
        from dazzle.core.ir.fields import FieldSpec as IRFieldSpec
        from dazzle.core.ir.fields import FieldType as IRFieldType
        from dazzle.core.ir.fields import FieldTypeKind
        from dazzle.core.ir.workspaces import WorkspaceRegion, WorkspaceSpec

        return AppSpec(
            name="test_app",
            version="1.0.0",
            domain=DomainSpec(
                entities=[
                    IREntitySpec(
                        name="Task",
                        title="Task",
                        fields=[
                            IRFieldSpec(
                                name="id",
                                type=IRFieldType(kind=FieldTypeKind.UUID),
                                modifiers=["pk"],
                            ),
                            IRFieldSpec(
                                name="title",
                                type=IRFieldType(kind=FieldTypeKind.STR, max_length=200),
                                modifiers=["required"],
                            ),
                        ],
                    ),
                    IREntitySpec(
                        name="Invoice",
                        title="Invoice",
                        fields=[
                            IRFieldSpec(
                                name="id",
                                type=IRFieldType(kind=FieldTypeKind.UUID),
                                modifiers=["pk"],
                            ),
                            IRFieldSpec(
                                name="amount",
                                type=IRFieldType(kind=FieldTypeKind.INT),
                                modifiers=["required"],
                            ),
                        ],
                    ),
                ]
            ),
            workspaces=[
                WorkspaceSpec(
                    name="overview",
                    title="Overview",
                    regions=[
                        WorkspaceRegion(name="tasks", source="Task"),
                        WorkspaceRegion(name="invoices", source="Invoice"),
                    ],
                ),
            ],
        )

    @pytest.fixture
    def batch_app(self, tmp_path: Any) -> Any:
        """Build a FastAPI app with a multi-region workspace."""
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
            builder = DazzleBackendApp(self._make_spec_with_aggregates(), config=config)
            return builder.build()

    def test_batch_endpoint_registered(self, batch_app: Any) -> None:
        """Batch endpoint should be registered for the workspace."""
        from fastapi.testclient import TestClient

        client = TestClient(batch_app, raise_server_exceptions=False)
        resp = client.get("/api/workspaces/overview/batch")
        assert resp.status_code == 200

    def test_batch_returns_region_data(self, batch_app: Any) -> None:
        """Batch endpoint should return data for all regions."""
        from fastapi.testclient import TestClient

        client = TestClient(batch_app, raise_server_exceptions=False)
        resp = client.get("/api/workspaces/overview/batch")
        assert resp.status_code == 200
        data = resp.json()
        assert "regions" in data
        region_names = [r["region"] for r in data["regions"]]
        assert "tasks" in region_names
        assert "invoices" in region_names


# ---------------------------------------------------------------------------
# Step 13 — Transition URL {id} substitution (#288)
# ---------------------------------------------------------------------------


class TestTransitionUrlSubstitution:
    """Transition api_url must have {id} replaced with actual entity ID."""

    def test_template_compiler_creates_transition_with_id_placeholder(self) -> None:
        """TransitionContext.api_url should contain {id} placeholder."""
        from dazzle_ui.runtime.template_context import TransitionContext

        t = TransitionContext(
            to_state="approved",
            label="Approve",
            api_url="/tasks/{id}",
        )
        assert "{id}" in t.api_url

    def test_transition_url_substitution_in_page_routes(self) -> None:
        """page_routes replaces {id} in transition.api_url with path_id."""
        from dazzle_ui.runtime.template_context import DetailContext, TransitionContext

        ctx_detail = DetailContext(
            entity_name="Task",
            title="Task Details",
            fields=[],
            transitions=[
                TransitionContext(
                    to_state="in_progress",
                    label="Start",
                    api_url="/tasks/{id}",
                ),
                TransitionContext(
                    to_state="done",
                    label="Complete",
                    api_url="/tasks/{id}",
                ),
            ],
        )
        # Simulate what page_routes does
        path_id = "abc-123-uuid"
        for _t in ctx_detail.transitions:
            if _t.api_url and "{id}" in _t.api_url:
                _t.api_url = _t.api_url.replace("{id}", str(path_id))

        assert ctx_detail.transitions[0].api_url == "/tasks/abc-123-uuid"
        assert ctx_detail.transitions[1].api_url == "/tasks/abc-123-uuid"

    @pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
    def test_detail_template_renders_transition_url(self) -> None:
        """Detail template renders transition buttons with resolved URLs."""
        html = render_fragment(
            "components/detail_view.html",
            detail=SimpleNamespace(
                entity_name="Task",
                title="Task Details",
                fields=[],
                item={"id": "t1", "title": "Fix bug", "status": "todo"},
                edit_url="/app/tasks/t1/edit",
                delete_url="/tasks/t1",
                back_url="/app/tasks",
                transitions=[
                    SimpleNamespace(
                        to_state="in_progress",
                        label="Start",
                        api_url="/tasks/t1",
                    ),
                ],
                status_field="status",
            ),
        )
        assert "Start" in html
        assert 'hx-put="/tasks/t1"' in html
        assert "{id}" not in html


# ---------------------------------------------------------------------------
# HTMX Column Injection Tests (issue #286)
# ---------------------------------------------------------------------------


class TestHtmxColumnInjection:
    """create_list_handler should inject HTMX metadata into request.state."""

    @pytest.mark.asyncio
    async def test_htmx_columns_set_on_request_state(self) -> None:
        """When htmx_columns is provided, it's set on request.state."""
        from dazzle_back.runtime.route_generator import create_list_handler

        columns = [{"key": "name", "label": "Name", "type": "text"}]

        async def mock_service_execute(**kwargs: Any) -> dict[str, Any]:
            return {"items": [], "total": 0}

        service = SimpleNamespace(execute=mock_service_execute)
        handler = create_list_handler(
            service,
            htmx_columns=columns,
            htmx_detail_url="/app/tasks/{id}",
            htmx_entity_name="Task",
        )

        request = SimpleNamespace(
            state=SimpleNamespace(),
            headers={},
            query_params={},
        )

        await handler(request=request, page=1, page_size=20, sort=None, dir="asc", search=None)

        assert request.state.htmx_columns == columns
        assert request.state.htmx_detail_url == "/app/tasks/{id}"
        assert request.state.htmx_entity_name == "Task"

    @pytest.mark.asyncio
    async def test_htmx_columns_default_empty_when_not_provided(self) -> None:
        """When htmx_columns is not provided, htmx_columns is not set on state."""
        from dazzle_back.runtime.route_generator import create_list_handler

        async def mock_service_execute(**kwargs: Any) -> dict[str, Any]:
            return {"items": [], "total": 0}

        service = SimpleNamespace(execute=mock_service_execute)
        handler = create_list_handler(service)

        request = SimpleNamespace(
            state=SimpleNamespace(),
            headers={},
            query_params={},
        )

        await handler(request=request, page=1, page_size=20, sort=None, dir="asc", search=None)

        assert not hasattr(request.state, "htmx_columns")


class TestHtmxTableRowRendering:
    """Table rows rendered by HTMX should include data cells when columns are present."""

    def test_table_rows_with_columns_render_data_cells(self) -> None:
        """When columns are provided, table rows render <td> elements with data."""
        from dazzle_ui.runtime.template_renderer import render_fragment

        table = {
            "rows": [
                {"id": "1", "first_name": "Jane", "email": "jane@test.com"},
                {"id": "2", "first_name": "John", "email": "john@test.com"},
            ],
            "columns": [
                {"key": "first_name", "label": "First Name", "type": "text"},
                {"key": "email", "label": "Email", "type": "text"},
            ],
            "detail_url_template": "/app/contact/{id}",
            "entity_name": "Contact",
            "api_endpoint": "/contacts",
            "table_id": "dt-contacts",
            "sort_field": "",
            "sort_dir": "asc",
            "filter_values": {},
            "page": 1,
            "page_size": 20,
            "total": 2,
            "empty_message": "No contacts found.",
            "bulk_actions": False,
        }

        html = render_fragment("fragments/table_rows.html", table=table)

        # Should contain actual data values
        assert "Jane" in html
        assert "jane@test.com" in html
        assert "John" in html

    def test_table_rows_without_columns_render_no_data(self) -> None:
        """When columns is empty, table rows render no <td> data cells."""
        from dazzle_ui.runtime.template_renderer import render_fragment

        table = {
            "rows": [
                {"id": "1", "first_name": "Jane", "email": "jane@test.com"},
            ],
            "columns": [],
            "detail_url_template": "/app/contact/{id}",
            "entity_name": "Contact",
            "api_endpoint": "/contacts",
            "table_id": "dt-contacts",
            "sort_field": "",
            "sort_dir": "asc",
            "filter_values": {},
            "page": 1,
            "page_size": 20,
            "total": 1,
            "empty_message": "No contacts found.",
            "bulk_actions": False,
        }

        html = render_fragment("fragments/table_rows.html", table=table)

        # Without columns, data values should NOT appear
        assert "Jane" not in html


# ---------------------------------------------------------------------------
# Async fetch helper tests (issue #286)
# ---------------------------------------------------------------------------


class TestAsyncFetch:
    """The async fetch helpers should not block the event loop."""

    @pytest.mark.asyncio
    async def test_fetch_json_returns_error_on_bad_pattern(self) -> None:
        """_fetch_json returns error dict when api_pattern has no {id}."""
        from dazzle_ui.runtime.page_routes import _fetch_json

        result = await _fetch_json("http://localhost:8000", "/contacts", "abc")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_fetch_json_returns_error_on_none_pattern(self) -> None:
        """_fetch_json returns error dict when api_pattern is None."""
        from dazzle_ui.runtime.page_routes import _fetch_json

        result = await _fetch_json("http://localhost:8000", None, "abc")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_fetch_json_returns_error_on_network_failure(self) -> None:
        """_fetch_json returns error dict when the HTTP request fails."""
        from dazzle_ui.runtime.page_routes import _fetch_json

        result = await _fetch_json("http://127.0.0.1:1", "/contacts/{id}", "abc")
        assert "error" in result
        assert result["id"] == "abc"
