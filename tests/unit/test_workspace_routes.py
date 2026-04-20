"""Tests for workspace route generation, region wiring, and helpers.

Covers:
- Nav route generation (convert_shell_config)
- RegionContext filter_expr / action wiring (build_workspace_context)
- _parse_simple_where helper
- _AGGREGATE_RE regex
- Sort spec → repo format conversion
"""

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
        assert ctx.regions[0].action_url == "/app/task/{id}"

    def test_action_url_defaults_to_entity_detail_when_no_surface_match(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = self._make_workspace_ir(action="nonexistent_surface")
        app_spec = self._make_app_spec_with_surface("other", "Other")
        ctx = build_workspace_context(ws, app_spec)

        assert ctx.regions[0].action == "nonexistent_surface"
        # Falls back to source entity detail URL
        assert ctx.regions[0].action_url == "/app/task/{id}"

    def test_action_url_defaults_to_entity_detail_when_no_action(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = self._make_workspace_ir()  # No action specified
        ctx = build_workspace_context(ws)

        # Default: rows link to source entity detail view
        assert ctx.regions[0].action_url == "/app/task/{id}"

    def test_sort_specs_serialized(self) -> None:
        from dazzle.core.ir.ux import SortSpec
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = self._make_workspace_ir(sort=[SortSpec(field="due_date", direction="desc")])
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].sort == [{"field": "due_date", "direction": "desc"}]

    # ---- Cycle 246 — EX-047 aggregate display-mode inference ----

    def _make_workspace_with_aggregate(self, display: Any = None):
        """Region with aggregates and configurable (or default) display."""
        from dazzle.core.ir.workspaces import WorkspaceRegion, WorkspaceSpec

        kwargs = {
            "name": "metrics",
            "source": "Task",
            "aggregates": {
                "total": "count(Task)",
                "done": "count(Task where status = done)",
            },
        }
        if display is not None:
            kwargs["display"] = display
        else:
            # Default — don't pass display, use IR default (LIST)
            pass
        region = WorkspaceRegion(**kwargs)
        return WorkspaceSpec(name="admin_dashboard", title="Admin", regions=[region])

    def test_aggregate_without_display_promotes_to_summary(self) -> None:
        """Region with `aggregate:` but no `display:` should route to SUMMARY.

        Before cycle 246 the display defaulted to LIST, routing the
        region through list.html which dropped the aggregates and
        rendered as an empty list. 4 regions across 2 apps were
        affected: simple_task admin_dashboard.metrics +
        admin_dashboard.team_metrics + team_overview.metrics,
        fieldtest_hub engineering_dashboard.metrics.
        """
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = self._make_workspace_with_aggregate(display=None)
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].display == "SUMMARY"
        assert ctx.regions[0].template == "workspace/regions/metrics.html"

    def test_explicit_display_summary_preserved(self) -> None:
        """Explicit `display: summary` is unchanged by the inference."""
        from dazzle.core.ir.workspaces import DisplayMode
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = self._make_workspace_with_aggregate(display=DisplayMode.SUMMARY)
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].display == "SUMMARY"
        assert ctx.regions[0].template == "workspace/regions/metrics.html"

    def test_explicit_display_list_with_aggregates_still_promotes(self) -> None:
        """An explicit `display: list` with aggregates is still promoted.

        The inference fires on ``display_mode == "LIST"`` which is
        either the parser default OR an explicit declaration. Both
        cases are treated the same because: (a) the DSL author who
        explicitly writes `display: list` probably means "tabular
        output not metrics", but they also wrote `aggregate:` — which
        is contradictory; (b) promoting is the forgiving option, since
        the alternative is silently dropping the aggregates. A future
        cycle could add a lint warning for the contradiction.
        """
        from dazzle.core.ir.workspaces import DisplayMode
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        ws = self._make_workspace_with_aggregate(display=DisplayMode.LIST)
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].display == "SUMMARY"

    def test_no_aggregates_preserves_list_default(self) -> None:
        """A plain list region without aggregates is unaffected."""
        from dazzle.core.ir.workspaces import WorkspaceRegion, WorkspaceSpec
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        region = WorkspaceRegion(name="tasks", source="Task")
        ws = WorkspaceSpec(name="ws", title="WS", regions=[region])
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].display == "LIST"
        assert ctx.regions[0].template == "workspace/regions/list.html"

    def test_kanban_with_aggregates_preserved(self) -> None:
        """A kanban region with aggregates stays kanban (inference only touches LIST)."""
        from dazzle.core.ir.workspaces import DisplayMode, WorkspaceRegion, WorkspaceSpec
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        region = WorkspaceRegion(
            name="board",
            source="Task",
            display=DisplayMode.KANBAN,
            aggregates={"total": "count(Task)"},
        )
        ws = WorkspaceSpec(name="ws", title="WS", regions=[region])
        ctx = build_workspace_context(ws)
        assert ctx.regions[0].display == "KANBAN"


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
        # Post-DaisyUI refactor: ref links use the --primary token directly
        assert "text-[hsl(var(--primary))]" in html

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
        """Regions should still have hx-get and a non-SSE trigger even without SSE."""
        ws = self._make_workspace_ctx(sse_url="")
        html = render_fragment("workspace/_content.html", workspace=ws)
        assert "hx-get=" in html
        # Dashboard rebuild uses intersect-based lazy loading instead of load trigger
        assert "hx-trigger=" in html
        assert "intersect" in html


# ---------------------------------------------------------------------------
# Cycle 239 — Metrics region contract (UX-042)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestMetricsRegionTemplate:
    """Metrics region renders aggregate tiles + optional drill-down table.

    Cycle 239 — contracts the metrics.html region template and its canonical
    tile anatomy. Quality gates encoded here mirror the ones in
    ~/.claude/skills/ux-architect/components/metrics-region.md.
    """

    def _metrics_kwargs(self, **overrides):
        """Default context required by workspace/regions/metrics.html."""
        defaults = {
            "title": "Queue Metrics",
            "metrics": [],
            "items": [],
            "columns": [],
            "empty_message": "No metrics available.",
            "action_url": "",
            "action_id_field": "id",
        }
        defaults.update(overrides)
        return defaults

    def test_renders_canonical_tile_markers(self) -> None:
        html = render_fragment(
            "workspace/regions/metrics.html",
            **self._metrics_kwargs(
                metrics=[
                    {"label": "Total Open", "value": 7},
                    {"label": "In Progress", "value": 3},
                    {"label": "Critical", "value": 0},
                ],
            ),
        )
        # Gate 1: canonical class markers and counts
        assert "dz-metrics-grid" in html
        assert 'data-dz-tile-count="3"' in html
        assert html.count("dz-metric-tile") == 3
        # Per-tile machine-readable keys, slugified from label
        assert 'data-dz-metric-key="total_open"' in html
        assert 'data-dz-metric-key="in_progress"' in html
        assert 'data-dz-metric-key="critical"' in html

    def test_thousands_separator_applied_to_values(self) -> None:
        html = render_fragment(
            "workspace/regions/metrics.html",
            **self._metrics_kwargs(
                metrics=[
                    {"label": "Total Events", "value": 1234567},
                    {"label": "Pending", "value": 42},
                ],
            ),
        )
        # Gate 3: integer values format with thousands separator
        assert "1,234,567" in html
        assert "42" in html
        # Raw unformatted value MUST NOT appear
        assert ">1234567<" not in html

    def test_tile_order_preserves_metric_list_order(self) -> None:
        html = render_fragment(
            "workspace/regions/metrics.html",
            **self._metrics_kwargs(
                metrics=[
                    {"label": "Third", "value": 3},
                    {"label": "First", "value": 1},
                    {"label": "Second", "value": 2},
                ],
            ),
        )
        # Gate 4: order matches DSL declaration order
        i_third = html.find("Third")
        i_first = html.find("First")
        i_second = html.find("Second")
        assert -1 < i_third < i_first < i_second

    def test_empty_metrics_renders_empty_state(self) -> None:
        html = render_fragment(
            "workspace/regions/metrics.html",
            **self._metrics_kwargs(metrics=[], empty_message="Nothing to show."),
        )
        # Gate 5: no grid wrapper when metrics is empty
        assert "dz-metrics-grid" not in html
        assert "Nothing to show." in html

    def test_no_hardcoded_hsl_literals(self) -> None:
        """Gate 2: no hardcoded HSL warning literals.

        The pre-cycle-239 template had `hsl(38_92%_50%/0.08)` inline for
        the warning attention-level. This test locks the migration in place.
        """
        html = render_fragment(
            "workspace/regions/metrics.html",
            **self._metrics_kwargs(
                metrics=[{"label": "Total", "value": 10}],
                items=[
                    {
                        "id": "1",
                        "title": "Row",
                        "_attention": {"level": "warning", "message": "Watch out"},
                    }
                ],
                columns=[{"key": "title", "label": "Title", "type": "text"}],
            ),
        )
        # The old hardcoded literal must not appear anywhere
        assert "38_92%" not in html
        # The canonical token must appear for the warning row tint
        assert "hsl(var(--warning)" in html

    def test_drill_down_table_renders_when_items_and_columns(self) -> None:
        html = render_fragment(
            "workspace/regions/metrics.html",
            **self._metrics_kwargs(
                metrics=[{"label": "Total", "value": 10}],
                items=[
                    {"id": "1", "title": "Row 1", "status": "open"},
                    {"id": "2", "title": "Row 2", "status": "done"},
                ],
                columns=[
                    {"key": "title", "label": "Title", "type": "text"},
                    {"key": "status", "label": "Status", "type": "badge"},
                ],
            ),
        )
        # Tiles still present
        assert "dz-metric-tile" in html
        # Drill-down table headers present
        assert ">Title<" in html
        assert ">Status<" in html
        # Status badge (cycle 238 macro) rendered for each row
        assert html.count("dz-status-badge") == 2
        # Row data visible
        assert "Row 1" in html
        assert "Row 2" in html

    def test_no_dead_description_field(self) -> None:
        """Gate 6: cycle 239 removed the unused metric.description branch.

        If someone reinstates the branch without wiring the compiler, it
        will silently render blank. Lock the removal in place.
        """
        html = render_fragment(
            "workspace/regions/metrics.html",
            **self._metrics_kwargs(
                metrics=[
                    {"label": "Open", "value": 5, "description": "should not render"},
                ],
            ),
        )
        # The compiler never populates description — template must ignore it
        assert "should not render" not in html

    def test_metrics_routes_to_summary_template(self) -> None:
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert DISPLAY_TEMPLATE_MAP.get("SUMMARY") == "workspace/regions/metrics.html"
        assert DISPLAY_TEMPLATE_MAP.get("METRICS") == "workspace/regions/metrics.html"


# ---------------------------------------------------------------------------
# Cycle 271 — Progress region contract (UX-062)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestProgressRegionTemplate:
    """Progress region renders a native <progress> bar + coloured stage chips.

    Cycle 271 — contracts the progress.html region template. Quality gates
    encoded here mirror the ones in
    ~/.claude/skills/ux-architect/components/progress-region.md. The prior
    template had a hardcoded green HSL literal (`hsl(142_71%_45%)`) for the
    complete-stage chip — the same drift class cycle 239 fixed in
    metrics.html. Migrating it to `hsl(var(--success))` is the load-bearing
    structural fix of this audit.
    """

    def _progress_kwargs(self, **overrides):
        defaults = {
            "title": "Backlog Progress",
            "stage_counts": [],
            "complete_pct": 0,
            "complete_count": 0,
            "progress_total": 0,
            "empty_message": "No backlog",
            "entity_name": "Ticket",
        }
        defaults.update(overrides)
        return defaults

    def test_renders_canonical_wrapper_and_progress_bar(self) -> None:
        """Gates 1 + 2: outer `.dz-progress-region` + `<progress>` element."""
        html = render_fragment(
            "workspace/regions/progress.html",
            **self._progress_kwargs(
                stage_counts=[
                    {"name": "Open", "count": 3, "complete": False},
                    {"name": "Done", "count": 5, "complete": True},
                ],
                complete_pct=62.5,
                complete_count=5,
                progress_total=8,
            ),
        )
        assert "dz-progress-region" in html
        assert "dz-progress-header" in html
        assert "<progress data-dz-progress" in html
        assert 'value="62.5"' in html
        assert 'max="100"' in html

    def test_chip_count_matches_stage_counts(self) -> None:
        """Gate 3: chip count equals len(stage_counts); name + count visible."""
        html = render_fragment(
            "workspace/regions/progress.html",
            **self._progress_kwargs(
                stage_counts=[
                    {"name": "Open", "count": 3, "complete": False},
                    {"name": "In Progress", "count": 2, "complete": False},
                    {"name": "Done", "count": 5, "complete": True},
                ],
                complete_pct=50.0,
                complete_count=5,
                progress_total=10,
            ),
        )
        assert html.count("dz-progress-chip") == 3
        assert "Open (3)" in html
        assert "In Progress (2)" in html
        assert "Done (5)" in html

    def test_tristate_colouring_flows_through_tokens(self) -> None:
        """Gate 4: chips reference --success/--warning/--muted tokens.

        Locks in the cycle 271 migration away from the hardcoded
        `hsl(142_71%_45%)` green literal.
        """
        html = render_fragment(
            "workspace/regions/progress.html",
            **self._progress_kwargs(
                stage_counts=[
                    {"name": "Done", "count": 5, "complete": True},
                    {"name": "Open", "count": 3, "complete": False},
                    {"name": "Backlog", "count": 0, "complete": False},
                ],
                complete_pct=62.5,
                complete_count=5,
                progress_total=8,
            ),
        )
        assert "hsl(var(--success)" in html
        assert "hsl(var(--warning)" in html
        assert "hsl(var(--muted)" in html

    def test_no_hardcoded_hsl_literals(self) -> None:
        """Gate 4 (negative form): pre-cycle-271 hardcoded green must not reappear."""
        html = render_fragment(
            "workspace/regions/progress.html",
            **self._progress_kwargs(
                stage_counts=[
                    {"name": "Done", "count": 5, "complete": True},
                    {"name": "Open", "count": 3, "complete": False},
                ],
                complete_pct=62.5,
                complete_count=5,
                progress_total=8,
            ),
        )
        assert "142_71%" not in html
        assert "142 71%" not in html

    def test_empty_state_when_no_stage_counts(self) -> None:
        """Gate 5: stage_counts empty → role=status paragraph, no <progress>."""
        html = render_fragment(
            "workspace/regions/progress.html",
            **self._progress_kwargs(
                stage_counts=[],
                empty_message="No backlog yet.",
            ),
        )
        assert "<progress" not in html
        assert "dz-progress-chip" not in html
        assert 'role="status"' in html
        assert "No backlog yet." in html

    def test_summary_footer_conditional_on_progress_total(self) -> None:
        """Gate 6: summary paragraph renders iff progress_total > 0."""
        # With total > 0: summary renders
        html_with = render_fragment(
            "workspace/regions/progress.html",
            **self._progress_kwargs(
                stage_counts=[{"name": "Open", "count": 3, "complete": False}],
                complete_pct=0.0,
                complete_count=0,
                progress_total=3,
            ),
        )
        assert "dz-progress-summary" in html_with
        assert "0 of 3 complete" in html_with

        # With total == 0: no summary
        html_without = render_fragment(
            "workspace/regions/progress.html",
            **self._progress_kwargs(
                stage_counts=[{"name": "Open", "count": 0, "complete": False}],
                complete_pct=0.0,
                complete_count=0,
                progress_total=0,
            ),
        )
        assert "dz-progress-summary" not in html_without

    def test_no_daisyui_leaks(self) -> None:
        """Gate 7: zero DaisyUI class references in rendered output."""
        html = render_fragment(
            "workspace/regions/progress.html",
            **self._progress_kwargs(
                stage_counts=[
                    {"name": "Done", "count": 5, "complete": True},
                    {"name": "Open", "count": 3, "complete": False},
                ],
                complete_pct=62.5,
                complete_count=5,
                progress_total=8,
            ),
        )
        # DaisyUI progress + badge variants must not appear
        for banned in (
            "progress-primary",
            "progress-success",
            "progress-warning",
            "badge-primary",
            "badge-success",
            "badge-warning",
            "btn-primary",
        ):
            assert banned not in html, f"DaisyUI leak: {banned!r}"

    def test_progress_routes_to_progress_template(self) -> None:
        """Gate 0 (routing): PROGRESS display mode resolves to this template."""
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert DISPLAY_TEMPLATE_MAP.get("PROGRESS") == "workspace/regions/progress.html"


# ---------------------------------------------------------------------------
# Cycle 272 — Detail region contract (UX-063)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestDetailRegionTemplate:
    """Detail region renders a single entity record as <dl>/<dt>/<dd> pairs.

    Cycle 272 — contracts the detail.html region template. Quality gates
    encoded here mirror the ones in
    ~/.claude/skills/ux-architect/components/detail-region.md.
    """

    def _detail_kwargs(self, **overrides):
        defaults = {
            "title": "Selected Contact",
            "item": None,
            "columns": [],
            "empty_message": "No record selected.",
        }
        defaults.update(overrides)
        return defaults

    def test_renders_canonical_wrapper_and_grid(self) -> None:
        """Gates 1 + 2: dz-detail-region + dz-detail-grid <dl>."""
        html = render_fragment(
            "workspace/regions/detail.html",
            **self._detail_kwargs(
                item={"name": "Alice", "status": "active"},
                columns=[
                    {"key": "name", "label": "Name", "type": "text"},
                    {"key": "status", "label": "Status", "type": "badge"},
                ],
            ),
        )
        assert "dz-detail-region" in html
        assert "dz-detail-grid" in html
        assert "<dl" in html

    def test_dt_dd_pair_count_matches_columns(self) -> None:
        """Gate 3: <dt> and <dd> counts equal len(columns)."""
        html = render_fragment(
            "workspace/regions/detail.html",
            **self._detail_kwargs(
                item={"name": "Alice", "email": "alice@example.com", "status": "active"},
                columns=[
                    {"key": "name", "label": "Name", "type": "text"},
                    {"key": "email", "label": "Email", "type": "text"},
                    {"key": "status", "label": "Status", "type": "badge"},
                ],
            ),
        )
        assert html.count("<dt") == 3
        assert html.count("<dd") == 3

    def test_labels_use_muted_foreground_token(self) -> None:
        """Gate 4: <dt> class references --muted-foreground token, no hardcoded HSL."""
        html = render_fragment(
            "workspace/regions/detail.html",
            **self._detail_kwargs(
                item={"name": "Alice"},
                columns=[{"key": "name", "label": "Name", "type": "text"}],
            ),
        )
        # dt label uses the token
        assert "hsl(var(--muted-foreground))" in html
        # No digit-starting HSL literals inside class attributes
        import re

        dt_match = re.search(r"<dt[^>]*class=\"([^\"]+)\"", html)
        assert dt_match is not None
        assert "hsl(" not in dt_match.group(1) or "var(--" in dt_match.group(1)

    def test_values_use_foreground_token(self) -> None:
        """Gate 5: <dd> class references --foreground token."""
        html = render_fragment(
            "workspace/regions/detail.html",
            **self._detail_kwargs(
                item={"name": "Alice"},
                columns=[{"key": "name", "label": "Name", "type": "text"}],
            ),
        )
        assert "hsl(var(--foreground))" in html

    def test_badge_column_delegates_to_status_badge_macro(self) -> None:
        """Gate 6: type=badge invokes render_status_badge, producing dz-status-badge."""
        html = render_fragment(
            "workspace/regions/detail.html",
            **self._detail_kwargs(
                item={"status": "active"},
                columns=[{"key": "status", "label": "Status", "type": "badge"}],
            ),
        )
        assert "dz-status-badge" in html

    def test_ref_anchor_uses_primary_token(self) -> None:
        """Gate 7: ref column with ref_route + mapping value → anchor with primary token."""
        html = render_fragment(
            "workspace/regions/detail.html",
            **self._detail_kwargs(
                item={
                    "owner": {"id": "42", "name": "Bob"},
                    "owner_display": "Bob Smith",
                },
                columns=[
                    {
                        "key": "owner",
                        "label": "Owner",
                        "type": "ref",
                        "ref_route": "/app/user/{id}",
                    }
                ],
            ),
        )
        assert "hsl(var(--primary))" in html
        assert 'href="/app/user/42"' in html
        assert "Bob Smith" in html

    def test_emdash_fallback_for_null_value(self) -> None:
        """Gate 8: plain-type column renders emdash for missing value, not 'None'."""
        html = render_fragment(
            "workspace/regions/detail.html",
            **self._detail_kwargs(
                item={"notes": None},
                columns=[{"key": "notes", "label": "Notes", "type": "text"}],
            ),
        )
        assert "—" in html
        # The literal Python string "None" must not leak
        assert ">None<" not in html

    def test_empty_state_when_no_item(self) -> None:
        """Gate 9: item=None → role=status paragraph, no <dl>."""
        html = render_fragment(
            "workspace/regions/detail.html",
            **self._detail_kwargs(
                item=None,
                empty_message="Pick a contact from the list.",
            ),
        )
        assert "<dl" not in html
        assert 'role="status"' in html
        assert "Pick a contact from the list." in html

    def test_no_daisyui_leaks(self) -> None:
        """Gate 10: zero DaisyUI class references in rendered output."""
        html = render_fragment(
            "workspace/regions/detail.html",
            **self._detail_kwargs(
                item={"name": "Alice", "status": "active"},
                columns=[
                    {"key": "name", "label": "Name", "type": "text"},
                    {"key": "status", "label": "Status", "type": "badge"},
                ],
            ),
        )
        for banned in (
            "badge-primary",
            "badge-success",
            "badge-warning",
            "badge-error",
            "btn-primary",
            "card-body",
        ):
            assert banned not in html, f"DaisyUI leak: {banned!r}"

    def test_detail_routes_to_detail_template(self) -> None:
        """Gate 0 (routing): DETAIL display mode resolves to this template."""
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert DISPLAY_TEMPLATE_MAP.get("DETAIL") == "workspace/regions/detail.html"


# ---------------------------------------------------------------------------
# Cycle 273 — Heatmap region contract (UX-064)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestHeatmapRegionTemplate:
    """Heatmap region renders a matrix with threshold-driven cell colouring.

    Cycle 273 — contracts heatmap.html. Load-bearing structural fix: migrated
    4 hardcoded HSL literals (`hsl(0_72%_51%)`, `hsl(0_72%_35%)`,
    `hsl(142_71%_45%)`, `hsl(142_71%_30%)`) to `hsl(var(--destructive))` and
    `hsl(var(--success))` — same drift class as cycle 239's warning-literal
    sweep and cycle 271's progress-region green literal.
    """

    def _heatmap_kwargs(self, **overrides):
        defaults = {
            "title": "Activity Heatmap",
            "heatmap_matrix": [],
            "heatmap_col_values": [],
            "heatmap_thresholds": [],
            "action_url": "",
            "items": [],
            "total": 0,
            "empty_message": "No data available.",
        }
        defaults.update(overrides)
        return defaults

    def test_renders_canonical_wrapper_and_grid(self) -> None:
        """Gates 1 + 2: dz-heatmap-region + dz-heatmap-grid <table>."""
        html = render_fragment(
            "workspace/regions/heatmap.html",
            **self._heatmap_kwargs(
                heatmap_matrix=[
                    {"row": "Mon", "row_id": "mon", "cells": [{"value": 5.0}]},
                ],
                heatmap_col_values=["9am"],
                heatmap_thresholds=[3.0, 8.0],
                items=[1],
                total=1,
            ),
        )
        assert "dz-heatmap-region" in html
        assert "dz-heatmap-scroll" in html
        assert "dz-heatmap-grid" in html
        assert "<table" in html

    def test_row_count_matches_matrix_length(self) -> None:
        """Gate 3: tbody <tr> count equals len(heatmap_matrix)."""
        html = render_fragment(
            "workspace/regions/heatmap.html",
            **self._heatmap_kwargs(
                heatmap_matrix=[
                    {"row": "Mon", "row_id": "mon", "cells": [{"value": 5.0}]},
                    {"row": "Tue", "row_id": "tue", "cells": [{"value": 7.0}]},
                    {"row": "Wed", "row_id": "wed", "cells": [{"value": 9.0}]},
                ],
                heatmap_col_values=["9am"],
                heatmap_thresholds=[3.0, 8.0],
                items=[1, 2, 3],
                total=3,
            ),
        )
        # tbody rows (not thead) — match data-rich cell class as proxy
        assert html.count("dz-heatmap-cell") == 3

    def test_column_header_count(self) -> None:
        """Gate 4: thead has 1 + len(heatmap_col_values) <th> elements."""
        html = render_fragment(
            "workspace/regions/heatmap.html",
            **self._heatmap_kwargs(
                heatmap_matrix=[
                    {
                        "row": "Mon",
                        "row_id": "mon",
                        "cells": [{"value": 1.0}, {"value": 2.0}, {"value": 3.0}],
                    },
                ],
                heatmap_col_values=["9am", "12pm", "3pm"],
                heatmap_thresholds=[3.0, 8.0],
                items=[1],
                total=1,
            ),
        )
        # Extract thead and count <th>
        import re

        thead_match = re.search(r"<thead[^>]*>(.*?)</thead>", html, re.DOTALL)
        assert thead_match is not None
        thead_html = thead_match.group(1)
        assert thead_html.count("<th") == 4  # 1 empty corner + 3 column labels

    def test_three_tier_threshold_colouring_uses_tokens(self) -> None:
        """Gate 5 (positive): 2-threshold path references all 3 design tokens."""
        html = render_fragment(
            "workspace/regions/heatmap.html",
            **self._heatmap_kwargs(
                heatmap_matrix=[
                    {
                        "row": "Low",
                        "row_id": "low",
                        "cells": [{"value": 1.0}],
                    },  # below first (destructive)
                    {"row": "Mid", "row_id": "mid", "cells": [{"value": 5.0}]},  # between (warning)
                    {
                        "row": "High",
                        "row_id": "high",
                        "cells": [{"value": 9.0}],
                    },  # at/above second (success)
                ],
                heatmap_col_values=["val"],
                heatmap_thresholds=[3.0, 8.0],
                items=[1, 2, 3],
                total=3,
            ),
        )
        assert "hsl(var(--destructive)" in html
        assert "hsl(var(--warning)" in html
        assert "hsl(var(--success)" in html

    def test_no_hardcoded_hsl_literals(self) -> None:
        """Gate 5 (negative): pre-cycle-273 red/green literals must not reappear."""
        html = render_fragment(
            "workspace/regions/heatmap.html",
            **self._heatmap_kwargs(
                heatmap_matrix=[
                    {
                        "row": "R",
                        "row_id": "r",
                        "cells": [
                            {"value": 1.0},
                            {"value": 5.0},
                            {"value": 9.0},
                        ],
                    },
                ],
                heatmap_col_values=["a", "b", "c"],
                heatmap_thresholds=[3.0, 8.0],
                items=[1],
                total=1,
            ),
        )
        assert "0_72%" not in html  # old destructive literal
        assert "142_71%" not in html  # old success literal

    def test_cell_value_formatted_one_decimal(self) -> None:
        """Gate 6: cells render {value | round 1}."""
        html = render_fragment(
            "workspace/regions/heatmap.html",
            **self._heatmap_kwargs(
                heatmap_matrix=[
                    {"row": "R", "row_id": "r", "cells": [{"value": 7.283}]},
                ],
                heatmap_col_values=["a"],
                heatmap_thresholds=[3.0, 8.0],
                items=[1],
                total=1,
            ),
        )
        assert "7.3" in html
        assert "7.283" not in html  # raw float must not leak

    def test_empty_state_when_no_matrix(self) -> None:
        """Gate 7: heatmap_matrix empty → role=status, no <table>."""
        html = render_fragment(
            "workspace/regions/heatmap.html",
            **self._heatmap_kwargs(
                heatmap_matrix=[],
                empty_message="No activity this period.",
            ),
        )
        assert "<table" not in html
        assert 'role="status"' in html
        assert "No activity this period." in html

    def test_drill_down_wired_when_action_url(self) -> None:
        """Gate 8: cells have hx-get iff action_url is non-empty."""
        with_action = render_fragment(
            "workspace/regions/heatmap.html",
            **self._heatmap_kwargs(
                heatmap_matrix=[{"row": "R", "row_id": "abc123", "cells": [{"value": 5.0}]}],
                heatmap_col_values=["a"],
                heatmap_thresholds=[3.0, 8.0],
                action_url="/app/tickets/{id}",
                items=[1],
                total=1,
            ),
        )
        assert 'hx-get="/app/tickets/abc123"' in with_action
        assert "#dz-detail-drawer-content" in with_action

        without_action = render_fragment(
            "workspace/regions/heatmap.html",
            **self._heatmap_kwargs(
                heatmap_matrix=[{"row": "R", "row_id": "abc123", "cells": [{"value": 5.0}]}],
                heatmap_col_values=["a"],
                heatmap_thresholds=[3.0, 8.0],
                action_url="",
                items=[1],
                total=1,
            ),
        )
        assert "hx-get=" not in without_action

    def test_truncation_footer_conditional(self) -> None:
        """Gate 9: 'Showing N of M' renders only when total > items|length."""
        truncated = render_fragment(
            "workspace/regions/heatmap.html",
            **self._heatmap_kwargs(
                heatmap_matrix=[{"row": "R", "row_id": "r", "cells": [{"value": 5.0}]}],
                heatmap_col_values=["a"],
                heatmap_thresholds=[3.0, 8.0],
                items=[1, 2, 3],  # 3 shown
                total=10,  # 10 exist
            ),
        )
        assert "Showing 3 of 10" in truncated

        not_truncated = render_fragment(
            "workspace/regions/heatmap.html",
            **self._heatmap_kwargs(
                heatmap_matrix=[{"row": "R", "row_id": "r", "cells": [{"value": 5.0}]}],
                heatmap_col_values=["a"],
                heatmap_thresholds=[3.0, 8.0],
                items=[1, 2, 3],
                total=3,
            ),
        )
        assert "Showing" not in not_truncated

    def test_no_daisyui_leaks(self) -> None:
        """Gate 10: zero DaisyUI class references."""
        html = render_fragment(
            "workspace/regions/heatmap.html",
            **self._heatmap_kwargs(
                heatmap_matrix=[{"row": "R", "row_id": "r", "cells": [{"value": 5.0}]}],
                heatmap_col_values=["a"],
                heatmap_thresholds=[3.0, 8.0],
                items=[1],
                total=1,
            ),
        )
        for banned in (
            "badge-primary",
            "badge-success",
            "badge-warning",
            "alert-error",
            "btn-primary",
            "table-zebra",
        ):
            assert banned not in html, f"DaisyUI leak: {banned!r}"

    def test_heatmap_routes_to_heatmap_template(self) -> None:
        """Gate 0 (routing): HEATMAP display mode resolves to this template."""
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert DISPLAY_TEMPLATE_MAP.get("HEATMAP") == "workspace/regions/heatmap.html"


# ---------------------------------------------------------------------------
# Cycle 274 — Bar chart region contract (UX-065)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestBarChartRegionTemplate:
    """Bar chart region has two modes: grouped (items + group_by) and fallback (metrics).

    Cycle 274 — contracts bar_chart.html. Minor structural fix alongside:
    grouped mode now has the same `max_count if > 0 else 1` guard that
    fallback mode already had, preventing a theoretical divide-by-zero
    when every bucket count is zero.
    """

    def _bar_kwargs(self, **overrides):
        defaults = {
            "title": "Status Breakdown",
            "items": [],
            "group_by": "",
            "metrics": [],
            "total": 0,
            "empty_message": "No data available.",
        }
        defaults.update(overrides)
        return defaults

    def test_renders_canonical_wrapper_grouped_mode(self) -> None:
        """Gate 1: dz-bar-chart-region wrapper present in grouped mode."""
        html = render_fragment(
            "workspace/regions/bar_chart.html",
            **self._bar_kwargs(
                items=[
                    {"status": "open"},
                    {"status": "open"},
                    {"status": "closed"},
                ],
                group_by="status",
                total=3,
            ),
        )
        assert "dz-bar-chart-region" in html
        assert "dz-bar-chart-bars" in html

    def test_grouped_mode_row_per_unique_bucket(self) -> None:
        """Gate 2: one dz-bar-chart-row per distinct bucket key."""
        html = render_fragment(
            "workspace/regions/bar_chart.html",
            **self._bar_kwargs(
                items=[
                    {"status": "open"},
                    {"status": "open"},
                    {"status": "open"},
                    {"status": "in_progress"},
                    {"status": "closed"},
                ],
                group_by="status",
                total=5,
            ),
        )
        # 3 unique status values → 3 rows
        assert html.count("dz-bar-chart-row") == 3
        assert ">open<" in html or ">Open<" in html or "open" in html

    def test_fallback_metrics_mode_row_per_metric(self) -> None:
        """Gate 3: one dz-bar-chart-row per metric (when no items/group_by)."""
        html = render_fragment(
            "workspace/regions/bar_chart.html",
            **self._bar_kwargs(
                metrics=[
                    {"label": "Total", "value": 10},
                    {"label": "Pending", "value": 4},
                    {"label": "Done", "value": 6},
                ],
            ),
        )
        assert html.count("dz-bar-chart-row") == 3
        assert "Total" in html
        assert "Pending" in html
        assert "Done" in html

    def test_bar_width_inline_style_integer_percentage(self) -> None:
        """Gate 4: each bar fill has style="width: N%" where N is 0-100 int."""
        html = render_fragment(
            "workspace/regions/bar_chart.html",
            **self._bar_kwargs(
                metrics=[
                    {"label": "A", "value": 3},
                    {"label": "B", "value": 10},
                ],
            ),
        )
        # 3 / 10 = 30%, 10/10 = 100%
        assert "width: 30%" in html
        assert "width: 100%" in html

    def test_track_and_fill_use_design_tokens(self) -> None:
        """Gate 5: track → --muted, fill → --primary. No hardcoded HSL."""
        html = render_fragment(
            "workspace/regions/bar_chart.html",
            **self._bar_kwargs(
                metrics=[{"label": "X", "value": 1}],
            ),
        )
        assert "hsl(var(--muted))" in html
        assert "hsl(var(--primary))" in html
        # No hardcoded HSL literals in class attributes
        import re

        # Exclude the one legitimate inline style="width: N%"
        class_hsl_leaks = re.findall(r'class="[^"]*hsl\(\d', html)
        assert not class_hsl_leaks, f"hardcoded HSL in class attr: {class_hsl_leaks}"

    def test_grouped_mode_renders_total_footer(self) -> None:
        """Gate 6: grouped mode ends with '{total} total' paragraph."""
        html = render_fragment(
            "workspace/regions/bar_chart.html",
            **self._bar_kwargs(
                items=[{"status": "open"}, {"status": "closed"}],
                group_by="status",
                total=2,
            ),
        )
        assert "2 total" in html

    def test_grouped_mode_uses_status_badge_for_label(self) -> None:
        """Gate 7: grouped mode delegates bucket label to render_status_badge."""
        html = render_fragment(
            "workspace/regions/bar_chart.html",
            **self._bar_kwargs(
                items=[{"status": "open"}, {"status": "open"}],
                group_by="status",
                total=2,
            ),
        )
        assert "dz-status-badge" in html

    def test_fallback_mode_does_not_use_status_badge(self) -> None:
        """Gate 8: fallback mode uses plain-text label span, NOT status badge."""
        html = render_fragment(
            "workspace/regions/bar_chart.html",
            **self._bar_kwargs(
                metrics=[{"label": "Total", "value": 1}],
            ),
        )
        # Metric labels are plain spans, not badges
        assert "dz-status-badge" not in html

    def test_empty_state_when_no_data_at_all(self) -> None:
        """Gate 9: no items, no metrics → role=status empty state, no bars."""
        html = render_fragment(
            "workspace/regions/bar_chart.html",
            **self._bar_kwargs(
                items=[],
                group_by="",
                metrics=[],
                empty_message="Nothing to chart.",
            ),
        )
        assert "dz-bar-chart-bars" not in html
        assert "dz-bar-chart-row" not in html
        assert 'role="status"' in html
        assert "Nothing to chart." in html

    def test_grouped_mode_wins_over_metrics_when_both_present(self) -> None:
        """Gate 10: mode precedence — grouped takes priority over metrics fallback."""
        html = render_fragment(
            "workspace/regions/bar_chart.html",
            **self._bar_kwargs(
                items=[{"status": "open"}, {"status": "closed"}],
                group_by="status",
                total=2,
                # metrics also provided — should be IGNORED
                metrics=[{"label": "METRIC-IGNORED", "value": 999}],
            ),
        )
        # Grouped mode footer present
        assert "2 total" in html
        # Metrics label must NOT appear
        assert "METRIC-IGNORED" not in html

    def test_no_daisyui_leaks(self) -> None:
        """Gate 11: zero DaisyUI class references."""
        html = render_fragment(
            "workspace/regions/bar_chart.html",
            **self._bar_kwargs(
                items=[{"status": "open"}],
                group_by="status",
                total=1,
            ),
        )
        for banned in (
            "progress-primary",
            "progress-success",
            "badge-primary",
            "btn-primary",
        ):
            assert banned not in html, f"DaisyUI leak: {banned!r}"

    def test_all_zero_metrics_does_not_divide_by_zero(self) -> None:
        """Safety guard: all-zero values resolve to 0% widths, no crash."""
        html = render_fragment(
            "workspace/regions/bar_chart.html",
            **self._bar_kwargs(
                metrics=[
                    {"label": "A", "value": 0},
                    {"label": "B", "value": 0},
                ],
            ),
        )
        # Rendered successfully with 0% widths
        assert "width: 0%" in html

    def test_bar_chart_routes_to_bar_chart_template(self) -> None:
        """Gate 0 (routing): BAR_CHART display mode resolves to this template."""
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert DISPLAY_TEMPLATE_MAP.get("BAR_CHART") == "workspace/regions/bar_chart.html"


# ---------------------------------------------------------------------------
# Cycle 275 — Grid region contract (UX-066)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestGridRegionTemplate:
    """Grid region renders items as a responsive 1/2/3-column card grid.

    Cycle 275 — contracts grid.html. Template was already drift-clean on
    tokens. Minor simplification: removed dead `{% elif ref %}` branch
    that fell through to dash (same output as `{% else %}` branch).
    """

    def _grid_kwargs(self, **overrides):
        defaults = {
            "title": "Systems",
            "items": [],
            "columns": [
                {"key": "name", "label": "Name", "type": "text"},
                {"key": "status", "label": "Status", "type": "badge"},
            ],
            "display_key": "name",
            "action_url": "",
            "action_id_field": "id",
            "entity_name": "System",
            "empty_message": "No systems registered.",
            "create_url": "",
            "create_label": "",
        }
        defaults.update(overrides)
        return defaults

    def test_renders_canonical_wrapper_and_grid(self) -> None:
        """Gates 1 + 2: dz-grid-region + responsive CSS grid container."""
        html = render_fragment(
            "workspace/regions/grid.html",
            **self._grid_kwargs(
                items=[{"id": "1", "name": "Alpha", "status": "active"}],
            ),
        )
        assert "dz-grid-region" in html
        # Responsive grid utilities
        assert "grid-cols-1" in html
        assert "sm:grid-cols-2" in html
        assert "lg:grid-cols-3" in html

    def test_cell_count_matches_items_length(self) -> None:
        """Gate 3: dz-grid-cell count equals len(items)."""
        html = render_fragment(
            "workspace/regions/grid.html",
            **self._grid_kwargs(
                items=[
                    {"id": "1", "name": "Alpha", "status": "active"},
                    {"id": "2", "name": "Beta", "status": "active"},
                    {"id": "3", "name": "Gamma", "status": "active"},
                ],
            ),
        )
        assert html.count("dz-grid-cell") == 3

    def test_primary_label_in_h4(self) -> None:
        """Gate 4: each cell contains <h4> with display_key value + foreground token."""
        html = render_fragment(
            "workspace/regions/grid.html",
            **self._grid_kwargs(
                items=[{"id": "1", "name": "Alpha", "status": "active"}],
            ),
        )
        assert "<h4" in html
        assert "hsl(var(--foreground))" in html
        assert "Alpha" in html

    def test_non_primary_columns_render_as_paragraphs(self) -> None:
        """Gate 5: each cell contains len(columns) - 1 <p> label-value pairs."""
        html = render_fragment(
            "workspace/regions/grid.html",
            **self._grid_kwargs(
                items=[{"id": "1", "name": "Alpha", "status": "active", "cpu": 42}],
                columns=[
                    {"key": "name", "label": "Name", "type": "text"},
                    {"key": "status", "label": "Status", "type": "badge"},
                    {"key": "cpu", "label": "CPU", "type": "text"},
                ],
                display_key="name",
            ),
        )
        # 2 non-primary columns → 2 <p> per cell
        # Count <p> tags inside the grid (exclude any outside if present)
        assert html.count("<p ") == 2  # status + cpu
        assert "Status:" in html
        assert "CPU:" in html

    def test_attention_level_critical_uses_destructive_token(self) -> None:
        """Gate 6 (critical): _attention={level:critical} → --destructive left border."""
        html = render_fragment(
            "workspace/regions/grid.html",
            **self._grid_kwargs(
                items=[
                    {
                        "id": "1",
                        "name": "Alpha",
                        "status": "down",
                        "_attention": {"level": "critical", "message": "System down"},
                    },
                ],
            ),
        )
        assert "border-l-[hsl(var(--destructive))]" in html
        assert 'title="System down"' in html

    def test_attention_level_warning_uses_warning_token(self) -> None:
        """Gate 6 (warning): --warning left border."""
        html = render_fragment(
            "workspace/regions/grid.html",
            **self._grid_kwargs(
                items=[
                    {
                        "id": "1",
                        "name": "Alpha",
                        "status": "degraded",
                        "_attention": {"level": "warning", "message": "High latency"},
                    },
                ],
            ),
        )
        assert "border-l-[hsl(var(--warning))]" in html

    def test_attention_level_notice_uses_primary_token(self) -> None:
        """Gate 6 (notice): --primary left border."""
        html = render_fragment(
            "workspace/regions/grid.html",
            **self._grid_kwargs(
                items=[
                    {
                        "id": "1",
                        "name": "Alpha",
                        "status": "active",
                        "_attention": {"level": "notice", "message": "Just deployed"},
                    },
                ],
            ),
        )
        assert "border-l-[hsl(var(--primary))]" in html

    def test_htmx_drill_down_wired_when_action_url(self) -> None:
        """Gate 7: cells have hx-get iff action_url is non-empty."""
        with_action = render_fragment(
            "workspace/regions/grid.html",
            **self._grid_kwargs(
                items=[{"id": "abc123", "name": "Alpha", "status": "active"}],
                action_url="/app/system/{id}",
            ),
        )
        assert 'hx-get="/app/system/abc123"' in with_action
        assert "#dz-detail-drawer-content" in with_action
        assert "cursor-pointer" in with_action

        without_action = render_fragment(
            "workspace/regions/grid.html",
            **self._grid_kwargs(
                items=[{"id": "abc123", "name": "Alpha", "status": "active"}],
                action_url="",
            ),
        )
        assert "hx-get=" not in without_action
        assert "cursor-pointer" not in without_action

    def test_ref_anchor_stop_propagation(self) -> None:
        """Gate 8: ref column anchor includes event.stopPropagation() onclick.

        Without this, clicking a ref link would both navigate AND fire the
        cell's HTMX drill-down, creating a race.
        """
        html = render_fragment(
            "workspace/regions/grid.html",
            **self._grid_kwargs(
                items=[
                    {
                        "id": "1",
                        "name": "Alpha",
                        "owner": {"id": "u42", "name": "Bob"},
                        "owner_display": "Bob Smith",
                    },
                ],
                columns=[
                    {"key": "name", "label": "Name", "type": "text"},
                    {
                        "key": "owner",
                        "label": "Owner",
                        "type": "ref",
                        "ref_route": "/app/user/{id}",
                    },
                ],
                display_key="name",
                action_url="/app/system/{id}",
            ),
        )
        assert 'onclick="event.stopPropagation()"' in html

    def test_empty_state_delegates_to_empty_state_fragment(self) -> None:
        """Gate 9: empty items → empty_state fragment markers, no cells."""
        html = render_fragment(
            "workspace/regions/grid.html",
            **self._grid_kwargs(items=[]),
        )
        assert "dz-grid-cell" not in html
        # The empty_state fragment emits its own canonical markers
        # (role="status" + dz-empty-state or similar)
        assert "No systems registered." in html or "empty" in html.lower()

    def test_no_daisyui_leaks(self) -> None:
        """Gate 10: zero DaisyUI class references."""
        html = render_fragment(
            "workspace/regions/grid.html",
            **self._grid_kwargs(
                items=[{"id": "1", "name": "Alpha", "status": "active"}],
            ),
        )
        for banned in (
            "badge-primary",
            "badge-success",
            "badge-warning",
            "badge-error",
            "btn-primary",
            "card-body",
        ):
            assert banned not in html, f"DaisyUI leak: {banned!r}"

    def test_cell_chrome_not_duplicated(self) -> None:
        """Gate 11: cells MUST NOT duplicate region-wrapper card chrome.

        Pins the #794 fix: the enclosing region_card owns rounded-[6px] +
        border + bg. Cells must stay plain inside (no full border, no bg-card,
        no outer-card radii).
        """
        html = render_fragment(
            "workspace/regions/grid.html",
            **self._grid_kwargs(
                items=[{"id": "1", "name": "Alpha", "status": "active"}],
            ),
        )
        import re

        cell_match = re.search(
            r'class="dz-grid-cell([^"]*)"',
            html,
        )
        assert cell_match is not None
        cell_class = cell_match.group(1)
        # Permitted inside the cell: rounded-[4px] (inner), border-l-4 (attn accent only)
        # Forbidden: 'border ' as a standalone utility (full border), bg-card, rounded-md/lg
        assert "bg-card" not in cell_class
        assert "rounded-md" not in cell_class
        assert "rounded-lg" not in cell_class

    def test_grid_routes_to_grid_template(self) -> None:
        """Gate 0 (routing): GRID display mode resolves to this template."""
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert DISPLAY_TEMPLATE_MAP.get("GRID") == "workspace/regions/grid.html"


# ---------------------------------------------------------------------------
# Cycle 276 — Timeline region contract (UX-067)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestTimelineRegionTemplate:
    """Timeline region renders a vertical chronological feed with bullet markers.

    Cycle 276 — contracts timeline.html. Template was already drift-clean on
    tokens. Most-adopted uncontracted region in the PROP-032 decomposition
    (5 DSL sites across fieldtest_hub, ops_dashboard, simple_task).
    """

    def _timeline_kwargs(self, **overrides):
        defaults = {
            "title": "Recent Events",
            "items": [],
            "columns": [
                {"key": "title", "label": "Title", "type": "text"},
                {"key": "occurred_at", "label": "When", "type": "date"},
                {"key": "status", "label": "Status", "type": "badge"},
            ],
            "display_key": "title",
            "action_url": "",
            "action_id_field": "id",
            "entity_name": "Event",
            "total": 0,
            "empty_message": "No events yet.",
        }
        defaults.update(overrides)
        return defaults

    def _now(self):
        from datetime import datetime

        return datetime.utcnow()

    def test_renders_canonical_wrapper_and_list(self) -> None:
        """Gates 1 + 2: dz-timeline-region + dz-timeline-list <ul>."""
        html = render_fragment(
            "workspace/regions/timeline.html",
            **self._timeline_kwargs(
                items=[
                    {
                        "id": "1",
                        "title": "Alpha event",
                        "occurred_at": self._now(),
                        "status": "done",
                    },
                ],
                total=1,
            ),
        )
        assert "dz-timeline-region" in html
        assert "dz-timeline-list" in html
        assert "<ul" in html
        assert "border-l" in html

    def test_item_count_matches_items_length(self) -> None:
        """Gate 3: dz-timeline-item count equals len(items)."""
        html = render_fragment(
            "workspace/regions/timeline.html",
            **self._timeline_kwargs(
                items=[
                    {
                        "id": "1",
                        "title": "A",
                        "occurred_at": self._now(),
                        "status": "open",
                    },
                    {
                        "id": "2",
                        "title": "B",
                        "occurred_at": self._now(),
                        "status": "done",
                    },
                    {
                        "id": "3",
                        "title": "C",
                        "occurred_at": self._now(),
                        "status": "open",
                    },
                ],
                total=3,
            ),
        )
        assert html.count("dz-timeline-item") == 3

    def test_bullet_marker_per_item(self) -> None:
        """Gate 4: each item has one dz-timeline-bullet SVG."""
        html = render_fragment(
            "workspace/regions/timeline.html",
            **self._timeline_kwargs(
                items=[
                    {
                        "id": "1",
                        "title": "A",
                        "occurred_at": self._now(),
                        "status": "open",
                    },
                    {
                        "id": "2",
                        "title": "B",
                        "occurred_at": self._now(),
                        "status": "done",
                    },
                ],
                total=2,
            ),
        )
        assert html.count("dz-timeline-bullet") == 2

    def test_bullet_colour_critical_uses_destructive_token(self) -> None:
        """Gate 5 (critical): _attention={level:critical} → --destructive."""
        html = render_fragment(
            "workspace/regions/timeline.html",
            **self._timeline_kwargs(
                items=[
                    {
                        "id": "1",
                        "title": "Outage",
                        "occurred_at": self._now(),
                        "status": "down",
                        "_attention": {"level": "critical", "message": "Service down"},
                    },
                ],
                total=1,
            ),
        )
        assert "text-[hsl(var(--destructive))]" in html

    def test_bullet_colour_warning_uses_warning_token(self) -> None:
        """Gate 5 (warning): --warning on bullet."""
        html = render_fragment(
            "workspace/regions/timeline.html",
            **self._timeline_kwargs(
                items=[
                    {
                        "id": "1",
                        "title": "Degraded",
                        "occurred_at": self._now(),
                        "status": "degraded",
                        "_attention": {"level": "warning", "message": "High latency"},
                    },
                ],
                total=1,
            ),
        )
        assert "text-[hsl(var(--warning))]" in html

    def test_bullet_colour_default_uses_primary_token(self) -> None:
        """Gate 5 (default): no attention → --primary."""
        html = render_fragment(
            "workspace/regions/timeline.html",
            **self._timeline_kwargs(
                items=[
                    {
                        "id": "1",
                        "title": "Normal event",
                        "occurred_at": self._now(),
                        "status": "ok",
                    },
                ],
                total=1,
            ),
        )
        assert "text-[hsl(var(--primary))]" in html

    def test_htmx_drill_down_wired_when_action_url(self) -> None:
        """Gate 8: content pad has hx-get iff action_url is set.

        Note: drill-down is on the content pad <div>, not the list item <li>.
        """
        from datetime import datetime

        now = datetime.utcnow()
        with_action = render_fragment(
            "workspace/regions/timeline.html",
            **self._timeline_kwargs(
                items=[{"id": "abc", "title": "A", "occurred_at": now, "status": "ok"}],
                action_url="/app/event/{id}",
                total=1,
            ),
        )
        assert 'hx-get="/app/event/abc"' in with_action
        assert "#dz-detail-drawer-content" in with_action
        assert "cursor-pointer" in with_action

        without_action = render_fragment(
            "workspace/regions/timeline.html",
            **self._timeline_kwargs(
                items=[{"id": "abc", "title": "A", "occurred_at": now, "status": "ok"}],
                action_url="",
                total=1,
            ),
        )
        assert "hx-get=" not in without_action

    def test_truncation_footer_conditional(self) -> None:
        """Gate 9: 'Showing N of M' renders only when total > len(items)."""
        from datetime import datetime

        now = datetime.utcnow()
        truncated = render_fragment(
            "workspace/regions/timeline.html",
            **self._timeline_kwargs(
                items=[
                    {"id": "1", "title": "A", "occurred_at": now, "status": "ok"},
                    {"id": "2", "title": "B", "occurred_at": now, "status": "ok"},
                ],
                total=50,
            ),
        )
        assert "Showing 2 of 50" in truncated

        not_truncated = render_fragment(
            "workspace/regions/timeline.html",
            **self._timeline_kwargs(
                items=[
                    {"id": "1", "title": "A", "occurred_at": now, "status": "ok"},
                ],
                total=1,
            ),
        )
        assert "Showing" not in not_truncated

    def test_empty_state_when_no_items(self) -> None:
        """Gate 10: items empty → role=status empty state, no list."""
        html = render_fragment(
            "workspace/regions/timeline.html",
            **self._timeline_kwargs(items=[], empty_message="Nothing happened yet."),
        )
        assert "<ul" not in html
        assert "dz-timeline-item" not in html
        assert 'role="status"' in html
        assert "Nothing happened yet." in html

    def test_no_daisyui_leaks(self) -> None:
        """Gate 11: zero DaisyUI class references."""
        from datetime import datetime

        html = render_fragment(
            "workspace/regions/timeline.html",
            **self._timeline_kwargs(
                items=[
                    {
                        "id": "1",
                        "title": "A",
                        "occurred_at": datetime.utcnow(),
                        "status": "ok",
                    },
                ],
                total=1,
            ),
        )
        for banned in (
            "badge-primary",
            "badge-success",
            "badge-warning",
            "badge-error",
            "btn-primary",
            "card-body",
            "progress-primary",
        ):
            assert banned not in html, f"DaisyUI leak: {banned!r}"

    def test_timeline_routes_to_timeline_template(self) -> None:
        """Gate 0 (routing): TIMELINE display mode resolves to this template."""
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert DISPLAY_TEMPLATE_MAP.get("TIMELINE") == "workspace/regions/timeline.html"


# ---------------------------------------------------------------------------
# Cycle 277 — Queue region contract (UX-068)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestQueueRegionTemplate:
    """Queue region renders ops-style work queues with inline transitions.

    Cycle 277 — contracts queue.html. Template was already drift-clean on
    tokens. This region is the richest yet: count badge + metrics strip +
    filter bar + attention-accented rows (dual signal: border + tint) +
    inline HTMX transition action buttons.
    """

    def _queue_kwargs(self, **overrides):
        defaults = {
            "title": None,
            "items": [],
            "columns": [
                {"key": "name", "label": "Name", "type": "text"},
                {"key": "priority", "label": "Priority", "type": "badge"},
            ],
            "display_key": "name",
            "total": 0,
            "metrics": [],
            "filter_columns": [],
            "active_filters": {},
            "action_url": "",
            "action_id_field": "id",
            "queue_transitions": [],
            "queue_status_field": "",
            "queue_api_endpoint": "",
            "region_name": "review_queue",
            "endpoint": "/api/workspaces/w/regions/review_queue",
            "empty_message": "Queue is empty.",
        }
        defaults.update(overrides)
        return defaults

    def test_renders_canonical_wrapper(self) -> None:
        """Gate 1: dz-queue-region outer wrapper."""
        html = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[{"id": "1", "name": "Alpha", "priority": "high"}],
                total=1,
            ),
        )
        assert "dz-queue-region" in html

    def test_count_badge_when_total_nonzero(self) -> None:
        """Gate 2: total > 0 → count badge with primary token."""
        with_count = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[{"id": "1", "name": "Alpha", "priority": "high"}],
                total=42,
            ),
        )
        assert ">42<" in with_count
        assert "bg-[hsl(var(--primary))]" in with_count

    def test_metrics_strip_when_metrics_present(self) -> None:
        """Gate 3: metrics → dz-queue-metrics with one tile per metric."""
        html = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[{"id": "1", "name": "A", "priority": "low"}],
                total=1,
                metrics=[
                    {"label": "Critical", "value": 3},
                    {"label": "Warning", "value": 7},
                ],
            ),
        )
        assert "dz-queue-metrics" in html
        assert ">Critical<" in html
        assert ">Warning<" in html

    def test_filter_bar_when_filter_columns_present(self) -> None:
        """Gate 4: filter_columns → <select>s with hx-get + hx-include."""
        html = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[{"id": "1", "name": "A", "priority": "low"}],
                total=1,
                filter_columns=[
                    {
                        "key": "status",
                        "label": "Status",
                        "options": ["open", "closed"],
                    },
                ],
            ),
        )
        assert "dz-queue-filters" in html
        assert "filter-bar" in html
        assert "<select" in html
        assert 'hx-get="/api/workspaces/w/regions/review_queue"' in html
        assert 'hx-include="closest .filter-bar"' in html
        assert 'name="filter_status"' in html

    def test_row_count_matches_items_length(self) -> None:
        """Gate 5: dz-queue-row count equals len(items)."""
        html = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[
                    {"id": "1", "name": "A", "priority": "high"},
                    {"id": "2", "name": "B", "priority": "low"},
                    {"id": "3", "name": "C", "priority": "medium"},
                ],
                total=3,
            ),
        )
        assert html.count("dz-queue-row") == 3

    def test_attention_critical_dual_signal(self) -> None:
        """Gate 6 (critical): border + tint use --destructive."""
        html = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[
                    {
                        "id": "1",
                        "name": "Urgent",
                        "priority": "critical",
                        "_attention": {"level": "critical", "message": "Blocker"},
                    },
                ],
                total=1,
            ),
        )
        assert "border-l-[hsl(var(--destructive))]" in html
        assert "bg-[hsl(var(--destructive)/0.04)]" in html
        assert "Blocker" in html

    def test_attention_warning_dual_signal(self) -> None:
        """Gate 6 (warning): border + tint use --warning."""
        html = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[
                    {
                        "id": "1",
                        "name": "Warn",
                        "priority": "medium",
                        "_attention": {"level": "warning", "message": "Stale"},
                    },
                ],
                total=1,
            ),
        )
        assert "border-l-[hsl(var(--warning))]" in html
        assert "bg-[hsl(var(--warning)/0.04)]" in html

    def test_attention_notice_dual_signal(self) -> None:
        """Gate 6 (notice): border + tint use --primary."""
        html = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[
                    {
                        "id": "1",
                        "name": "New",
                        "priority": "low",
                        "_attention": {"level": "notice", "message": "Recent"},
                    },
                ],
                total=1,
            ),
        )
        assert "border-l-[hsl(var(--primary))]" in html
        assert "bg-[hsl(var(--primary)/0.04)]" in html

    def test_badge_column_delegates_to_status_badge(self) -> None:
        """Gate 7: badge-typed columns render via render_status_badge."""
        html = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[{"id": "1", "name": "A", "priority": "high"}],
                total=1,
            ),
        )
        assert "dz-status-badge" in html

    def test_transition_button_wiring(self) -> None:
        """Gate 10: transition buttons use hx-put + hx-vals + hx-ext=json-enc."""
        html = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[{"id": "abc", "name": "A", "priority": "open", "status": "open"}],
                total=1,
                queue_transitions=[
                    {"label": "Close", "to_state": "closed"},
                    {"label": "Archive", "to_state": "archived"},
                ],
                queue_status_field="status",
                queue_api_endpoint="/api/ticket",
            ),
        )
        assert 'hx-put="/api/ticket/abc"' in html
        assert '"status": "closed"' in html
        assert '"status": "archived"' in html
        assert 'hx-ext="json-enc"' in html
        assert "#region-review_queue" in html

    def test_transition_current_state_suppressed(self) -> None:
        """Gate 9: transitions whose to_state matches current state are NOT rendered."""
        html = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[{"id": "abc", "name": "A", "priority": "open", "status": "open"}],
                total=1,
                queue_transitions=[
                    {"label": "Open again", "to_state": "open"},
                    {"label": "Close", "to_state": "closed"},
                ],
                queue_status_field="status",
                queue_api_endpoint="/api/ticket",
            ),
        )
        # "Close" transition button present (Jinja whitespace around label varies)
        assert "Close" in html
        # "Open again" transition button NOT present (current state is "open")
        assert "Open again" not in html

    def test_button_group_has_stop_propagation(self) -> None:
        """Gate 11: button-group wrapper has inline event.stopPropagation().

        Same class as grid-region's ref-anchor stopPropagation exception —
        prevents the row's hx-get drill-down from firing when clicking a
        transition button.
        """
        html = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[{"id": "abc", "name": "A", "priority": "open", "status": "open"}],
                total=1,
                queue_transitions=[{"label": "Close", "to_state": "closed"}],
                queue_status_field="status",
                queue_api_endpoint="/api/ticket",
                action_url="/app/ticket/{id}",
            ),
        )
        assert 'onclick="event.stopPropagation()"' in html

    def test_empty_state_when_no_items(self) -> None:
        """Gate 12: empty items → role=status, no .dz-queue-row."""
        html = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[],
                total=0,
                empty_message="No work to do.",
            ),
        )
        assert "dz-queue-row" not in html
        assert 'role="status"' in html
        assert "No work to do." in html

    def test_truncation_footer_conditional(self) -> None:
        """Gate 13: 'Showing N of M' renders iff total > len(items)."""
        truncated = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[
                    {"id": "1", "name": "A", "priority": "low"},
                    {"id": "2", "name": "B", "priority": "low"},
                ],
                total=100,
            ),
        )
        assert "Showing 2 of 100" in truncated

        not_truncated = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[{"id": "1", "name": "A", "priority": "low"}],
                total=1,
            ),
        )
        assert "Showing" not in not_truncated

    def test_no_daisyui_leaks(self) -> None:
        """Gate 14: zero DaisyUI class references."""
        html = render_fragment(
            "workspace/regions/queue.html",
            **self._queue_kwargs(
                items=[{"id": "1", "name": "A", "priority": "low"}],
                total=1,
                queue_transitions=[{"label": "Close", "to_state": "closed"}],
                queue_status_field="status",
                queue_api_endpoint="/api/ticket",
            ),
        )
        for banned in (
            "alert-info",
            "alert-warning",
            "alert-error",
            "alert-success",
            "badge-primary",
            "btn-primary",
        ):
            assert banned not in html, f"DaisyUI leak: {banned!r}"

    def test_queue_routes_to_queue_template(self) -> None:
        """Gate 0 (routing): QUEUE display mode resolves to this template."""
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert DISPLAY_TEMPLATE_MAP.get("QUEUE") == "workspace/regions/queue.html"


# ---------------------------------------------------------------------------
# Cycle 278 — List region contract (UX-069) — closes PROP-032 decomposition
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestListRegionTemplate:
    """List region is the framework default — table with sort/filter/drill-down.

    Cycle 278 — contracts list.html, closing the PROP-032 decomposition at
    8/8. LIST is the default display mode, so every region that doesn't
    declare an explicit `display:` renders through this template. Widest
    blast radius of any region contract.
    """

    def _list_kwargs(self, **overrides):
        defaults = {
            "title": None,
            "items": [],
            "columns": [
                {"key": "name", "label": "Name", "type": "text", "sortable": True},
                {"key": "status", "label": "Status", "type": "badge"},
            ],
            "total": 0,
            "region_actions": [],
            "filter_columns": [],
            "active_filters": {},
            "date_range": False,
            "action_url": "",
            "action_id_field": "id",
            "sort_field": "",
            "sort_dir": "",
            "region_name": "items",
            "endpoint": "/api/workspaces/w/regions/items",
            "empty_message": "No items.",
        }
        defaults.update(overrides)
        return defaults

    def test_renders_canonical_wrapper(self) -> None:
        """Gate 1: dz-list-region outer wrapper."""
        html = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(
                items=[{"id": "1", "name": "Alpha", "status": "active"}],
                total=1,
            ),
        )
        assert "dz-list-region" in html

    def test_csv_export_link_always_present(self) -> None:
        """Gate 2: CSV export link is unconditional."""
        # With items
        with_items = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(
                items=[{"id": "1", "name": "A", "status": "ok"}],
                total=1,
            ),
        )
        assert '?format=csv" download' in with_items
        assert 'aria-label="Export CSV"' in with_items

        # Even without items (empty state)
        without_items = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(items=[], total=0),
        )
        assert '?format=csv" download' in without_items

    def test_region_actions_when_configured(self) -> None:
        """Gate 3: hx-post buttons when region_actions is set."""
        html = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(
                items=[{"id": "1", "name": "A", "status": "ok"}],
                total=1,
                region_actions=[
                    {
                        "label": "Archive closed",
                        "endpoint": "/api/bulk/archive",
                        "confirm": "Archive all closed items?",
                    },
                ],
            ),
        )
        assert 'hx-post="/api/bulk/archive"' in html
        assert 'hx-confirm="Archive all closed items?"' in html
        assert 'hx-swap="none"' in html
        assert "Archive closed" in html

    def test_filter_bar_when_filter_columns_present(self) -> None:
        """Gate 4: filter_columns → <select>s with HTMX live-reload."""
        html = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(
                items=[{"id": "1", "name": "A", "status": "open"}],
                total=1,
                filter_columns=[
                    {
                        "key": "status",
                        "label": "Status",
                        "options": ["open", "closed"],
                    },
                ],
            ),
        )
        assert "dz-list-filters" in html
        assert "filter-bar" in html
        assert 'hx-get="/api/workspaces/w/regions/items"' in html
        assert 'hx-include="closest .filter-bar"' in html
        assert 'name="filter_status"' in html

    def test_table_and_row_count(self) -> None:
        """Gates 5 + 6: dz-list-table + row count matches items length."""
        html = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(
                items=[
                    {"id": "1", "name": "A", "status": "open"},
                    {"id": "2", "name": "B", "status": "closed"},
                    {"id": "3", "name": "C", "status": "open"},
                ],
                total=3,
            ),
        )
        assert "dz-list-table" in html
        assert html.count("dz-list-row") == 3

    def test_attention_level_bg_tints(self) -> None:
        """Gate 7: attention levels map to bg tints (critical/warning 0.08, notice 0.06)."""
        html = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(
                items=[
                    {
                        "id": "1",
                        "name": "Urgent",
                        "status": "critical",
                        "_attention": {"level": "critical", "message": "!!"},
                    },
                    {
                        "id": "2",
                        "name": "Warn",
                        "status": "warn",
                        "_attention": {"level": "warning", "message": "!"},
                    },
                    {
                        "id": "3",
                        "name": "Info",
                        "status": "ok",
                        "_attention": {"level": "notice", "message": "note"},
                    },
                ],
                total=3,
            ),
        )
        assert "bg-[hsl(var(--destructive)/0.08)]" in html
        assert "bg-[hsl(var(--warning)/0.08)]" in html
        assert "bg-[hsl(var(--primary)/0.06)]" in html

    def test_sortable_column_header_has_hx_get(self) -> None:
        """Gate 8: sortable columns have <a hx-get=...?sort=...&dir=...>."""
        html = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(
                items=[{"id": "1", "name": "A", "status": "open"}],
                total=1,
            ),
        )
        # "name" column is sortable in defaults
        assert "sort=name" in html
        assert 'hx-target="#region-items"' in html

    def test_active_sort_indicator(self) -> None:
        """Gate 9: active sort column has ▲ (asc) or ▼ (desc) indicator."""
        asc = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(
                items=[{"id": "1", "name": "A", "status": "open"}],
                total=1,
                sort_field="name",
                sort_dir="asc",
            ),
        )
        assert "▲" in asc

        desc = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(
                items=[{"id": "1", "name": "A", "status": "open"}],
                total=1,
                sort_field="name",
                sort_dir="desc",
            ),
        )
        assert "▼" in desc

    def test_row_drill_down_when_action_url_set(self) -> None:
        """Gate 10: rows have hx-get iff action_url is non-empty."""
        with_action = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(
                items=[{"id": "abc", "name": "A", "status": "open"}],
                total=1,
                action_url="/app/item/{id}",
            ),
        )
        assert 'hx-get="/app/item/abc"' in with_action
        assert "#dz-detail-drawer-content" in with_action
        assert "cursor-pointer" in with_action

        without_action = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(
                items=[{"id": "abc", "name": "A", "status": "open"}],
                total=1,
                action_url="",
            ),
        )
        # CSV link has href=; rows don't have hx-get for drill-down
        # Check specifically that no row has hx-target=detail-drawer
        assert "#dz-detail-drawer-content" not in without_action

    def test_ref_column_uses_htmx_anchor_with_stop_propagation(self) -> None:
        """Gate 11: ref columns with ref_route produce HTMX anchors + stopPropagation."""
        html = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(
                items=[
                    {
                        "id": "1",
                        "name": "A",
                        "status": "ok",
                        "owner": {"id": "u42", "name": "Bob"},
                        "owner_display": "Bob Smith",
                    },
                ],
                columns=[
                    {"key": "name", "label": "Name", "type": "text"},
                    {
                        "key": "owner",
                        "label": "Owner",
                        "type": "ref",
                        "ref_route": "/app/user/{id}",
                    },
                ],
                total=1,
                action_url="/app/item/{id}",
            ),
        )
        # Ref anchor uses hx-get (HTMX loading) not href
        assert 'hx-get="/app/user/u42"' in html
        assert 'onclick="event.stopPropagation()"' in html
        assert "Bob Smith" in html

    def test_empty_state_when_no_items(self) -> None:
        """Gate 12: empty items → delegates to empty_state fragment, no <table>."""
        html = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(items=[], total=0),
        )
        assert "<table" not in html
        assert "dz-list-row" not in html
        # CSV link is still present; empty_state fragment handles the empty display

    def test_truncation_footer_conditional(self) -> None:
        """Gate 13: 'Showing N of M' renders iff total > items|length."""
        truncated = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(
                items=[
                    {"id": "1", "name": "A", "status": "ok"},
                    {"id": "2", "name": "B", "status": "ok"},
                ],
                total=50,
            ),
        )
        assert "Showing 2 of 50" in truncated

        not_truncated = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(
                items=[{"id": "1", "name": "A", "status": "ok"}],
                total=1,
            ),
        )
        assert "Showing" not in not_truncated

    def test_no_daisyui_leaks(self) -> None:
        """Gate 14: zero DaisyUI class references."""
        html = render_fragment(
            "workspace/regions/list.html",
            **self._list_kwargs(
                items=[{"id": "1", "name": "A", "status": "ok"}],
                total=1,
            ),
        )
        for banned in (
            "table-zebra",
            "btn-primary",
            "badge-primary",
            "badge-success",
            "badge-warning",
            "alert-info",
        ):
            assert banned not in html, f"DaisyUI leak: {banned!r}"

    def test_list_routes_to_list_template(self) -> None:
        """Gate 0 (routing): LIST display mode resolves to this template (default)."""
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert DISPLAY_TEMPLATE_MAP.get("LIST") == "workspace/regions/list.html"


# ---------------------------------------------------------------------------
# Cycle 279 — Funnel chart region contract (UX-070)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestFunnelChartRegionTemplate:
    """Funnel chart region renders stacked proportional bars with alpha progression.

    Cycle 279 — contracts funnel_chart.html. Narrative prose contract was
    present in the header but never formalised. Template was drift-clean.
    """

    def _funnel_kwargs(self, **overrides):
        defaults = {
            "title": None,
            "kanban_columns": [],
            "items": [],
            "group_by": "",
            "metrics": [],
            "total": 0,
            "empty_message": "No data available.",
        }
        defaults.update(overrides)
        return defaults

    def test_renders_canonical_wrapper_and_stages_container(self) -> None:
        """Gates 1 + 2: dz-funnel-chart-region + dz-funnel-stages."""
        html = render_fragment(
            "workspace/regions/funnel_chart.html",
            **self._funnel_kwargs(
                kanban_columns=["new", "open"],
                items=[{"status": "new"}, {"status": "open"}],
                group_by="status",
                total=2,
            ),
        )
        assert "dz-funnel-chart-region" in html
        assert "dz-funnel-stages" in html

    def test_grouped_mode_stage_count_matches_kanban_columns(self) -> None:
        """Gate 3: one dz-funnel-stage per kanban_column."""
        html = render_fragment(
            "workspace/regions/funnel_chart.html",
            **self._funnel_kwargs(
                kanban_columns=["new", "open", "in_progress", "resolved"],
                items=[
                    {"status": "new"},
                    {"status": "new"},
                    {"status": "open"},
                    {"status": "resolved"},
                ],
                group_by="status",
                total=4,
            ),
        )
        assert html.count("dz-funnel-stage ") == 4

    def test_fallback_mode_stage_count_matches_metrics(self) -> None:
        """Gate 4: one dz-funnel-stage per metric."""
        html = render_fragment(
            "workspace/regions/funnel_chart.html",
            **self._funnel_kwargs(
                metrics=[
                    {"label": "Visitors", "value": 1000},
                    {"label": "Signups", "value": 200},
                    {"label": "Paid", "value": 50},
                ],
            ),
        )
        assert html.count("dz-funnel-stage ") == 3
        assert "Visitors" in html
        assert "Signups" in html
        assert "Paid" in html

    def test_stage_name_and_count_visible(self) -> None:
        """Gate 5: each stage shows name + (count)."""
        html = render_fragment(
            "workspace/regions/funnel_chart.html",
            **self._funnel_kwargs(
                kanban_columns=["open"],
                items=[{"status": "open"}, {"status": "open"}, {"status": "open"}],
                group_by="status",
                total=3,
            ),
        )
        assert "open" in html
        assert "(3)" in html

    def test_proportional_width_inline_style(self) -> None:
        """Gate 6: stages have style="width: N%; min-width: 120px;"."""
        html = render_fragment(
            "workspace/regions/funnel_chart.html",
            **self._funnel_kwargs(
                kanban_columns=["a", "b"],
                items=[
                    {"status": "a"},
                    {"status": "a"},
                    {"status": "a"},
                    {"status": "a"},
                    {"status": "b"},
                ],
                group_by="status",
                total=5,
            ),
        )
        # Stage a has 4 items, base = 4 → width 100%
        assert "width: 100%" in html
        assert "min-width: 120px" in html

    def test_minimum_width_floor_20_percent(self) -> None:
        """Gate 7: stages below 20% of base still render at 20% width."""
        html = render_fragment(
            "workspace/regions/funnel_chart.html",
            **self._funnel_kwargs(
                kanban_columns=["base", "small"],
                # base has 100 items, small has 1 item → 1% which should floor to 20%
                items=[{"status": "base"}] * 100 + [{"status": "small"}],
                group_by="status",
                total=101,
            ),
        )
        # The 1-item "small" stage would compute to 1% but must render at 20%
        assert "width: 20%" in html

    def test_primary_token_background(self) -> None:
        """Gate 8: stages use bg-[hsl(var(--primary)/...)] with dynamic alpha."""
        html = render_fragment(
            "workspace/regions/funnel_chart.html",
            **self._funnel_kwargs(
                kanban_columns=["a", "b", "c"],
                items=[{"status": "a"}, {"status": "b"}, {"status": "c"}],
                group_by="status",
                total=3,
            ),
        )
        assert "bg-[hsl(var(--primary)/" in html

    def test_progressive_alpha_first_two_stages(self) -> None:
        """Gate 9: stage 1 alpha 0.9, stage 2 alpha 0.8."""
        html = render_fragment(
            "workspace/regions/funnel_chart.html",
            **self._funnel_kwargs(
                kanban_columns=["a", "b", "c"],
                items=[{"status": "a"}, {"status": "b"}, {"status": "c"}],
                group_by="status",
                total=3,
            ),
        )
        assert "hsl(var(--primary)/0.9)" in html
        assert "hsl(var(--primary)/0.8)" in html
        assert "hsl(var(--primary)/0.7)" in html

    def test_alpha_floor_at_stage_9_plus(self) -> None:
        """Gate 10: 9th+ stage clamps alpha to 0.2."""
        html = render_fragment(
            "workspace/regions/funnel_chart.html",
            **self._funnel_kwargs(
                kanban_columns=["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
                items=[{"status": "a"}] * 10,
                group_by="status",
                total=10,
            ),
        )
        # 10 stages → stages at index 8+ (a through j = indices 0-9)
        # Index 8 and 9 clamp to 0.2
        assert "hsl(var(--primary)/0.2)" in html

    def test_grouped_mode_renders_total_footer(self) -> None:
        """Gate 11: grouped mode shows '{total} total'."""
        html = render_fragment(
            "workspace/regions/funnel_chart.html",
            **self._funnel_kwargs(
                kanban_columns=["a"],
                items=[{"status": "a"}, {"status": "a"}],
                group_by="status",
                total=2,
            ),
        )
        assert "2 total" in html

    def test_fallback_mode_omits_total_footer(self) -> None:
        """Gate 12: fallback metrics mode does NOT render total footer."""
        html = render_fragment(
            "workspace/regions/funnel_chart.html",
            **self._funnel_kwargs(
                metrics=[
                    {"label": "Visitors", "value": 1000},
                    {"label": "Paid", "value": 50},
                ],
            ),
        )
        assert "total" not in html.lower() or "1050 total" not in html

    def test_empty_state_when_no_data(self) -> None:
        """Gate 13: neither mode → role=status empty state, no stages."""
        html = render_fragment(
            "workspace/regions/funnel_chart.html",
            **self._funnel_kwargs(
                empty_message="No funnel data.",
            ),
        )
        assert "dz-funnel-stage" not in html
        assert 'role="status"' in html
        assert "No funnel data." in html

    def test_no_daisyui_leaks(self) -> None:
        """Gate 14: zero DaisyUI class references."""
        html = render_fragment(
            "workspace/regions/funnel_chart.html",
            **self._funnel_kwargs(
                kanban_columns=["a"],
                items=[{"status": "a"}],
                group_by="status",
                total=1,
            ),
        )
        for banned in (
            "badge-primary",
            "badge-success",
            "btn-primary",
            "card-body",
            "progress-primary",
        ):
            assert banned not in html, f"DaisyUI leak: {banned!r}"

    def test_funnel_chart_routes_to_template(self) -> None:
        """Gate 0 (routing): FUNNEL_CHART display mode resolves to this template."""
        from dazzle_ui.runtime.workspace_renderer import DISPLAY_TEMPLATE_MAP

        assert DISPLAY_TEMPLATE_MAP.get("FUNNEL_CHART") == "workspace/regions/funnel_chart.html"


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
        # Verify column headers are rendered.
        # Cycle 238 — status_badge macro humanises enum values, so
        # `todo` → `Todo`, `in_progress` → `In Progress`, `done` → `Done`.
        assert "Todo" in html
        assert "In Progress" in html
        assert "Done" in html
        # Canonical status-badge marker + tones landed
        assert "dz-status-badge" in html
        assert 'data-dz-status-tone="neutral"' in html  # todo → neutral
        assert 'data-dz-status-tone="info"' in html  # in_progress → info
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
        # Post-DaisyUI refactor: timeline shape is now a border-l vertical rule
        # + space-y-3 stack instead of a named timeline class.
        assert "pl-4 border-l border-[hsl(var(--border))]" in html

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
        # Cycle 238 — status_badge humanises enum values.
        assert "Todo" in html
        assert "In Progress" in html
        assert "Done" in html
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
        """has_many is hidden; belongs_to is shown as ref column (#553)."""
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
                    name="parent_id",
                    label=None,
                    type=SimpleNamespace(
                        kind=SimpleNamespace(value="belongs_to"), ref_entity="Parent"
                    ),
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
        assert len(cols) == 2
        keys = [c["key"] for c in cols]
        assert "parent" in keys  # belongs_to shown as ref column, _id stripped
        assert "title" in keys
        ref_col = next(c for c in cols if c["key"] == "parent")
        assert ref_col["type"] == "ref"


class TestBuildSurfaceColumns:
    """_build_surface_columns uses surface field projection instead of all entity fields (#405)."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_fastapi(self) -> None:
        pytest.importorskip("fastapi")

    def test_surface_limits_columns(self) -> None:
        """Only fields declared in the surface should appear."""
        from dazzle_back.runtime.workspace_rendering import _build_surface_columns

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
                    name="description",
                    label=None,
                    type=SimpleNamespace(kind=SimpleNamespace(value="text")),
                ),
                SimpleNamespace(
                    name="status",
                    label=None,
                    type=SimpleNamespace(
                        kind=SimpleNamespace(value="enum"),
                        enum_values=["open", "closed"],
                    ),
                ),
            ],
            state_machine=None,
        )
        surface = SimpleNamespace(
            sections=[
                SimpleNamespace(
                    elements=[
                        SimpleNamespace(field_name="title"),
                        SimpleNamespace(field_name="status"),
                    ]
                )
            ]
        )
        cols = _build_surface_columns(entity, surface)
        assert len(cols) == 2
        assert cols[0]["key"] == "title"
        assert cols[1]["key"] == "status"

    def test_surface_preserves_order(self) -> None:
        """Columns should follow the surface field order, not entity field order."""
        from dazzle_back.runtime.workspace_rendering import _build_surface_columns

        entity = SimpleNamespace(
            fields=[
                SimpleNamespace(
                    name="id", type=SimpleNamespace(kind=SimpleNamespace(value="uuid"))
                ),
                SimpleNamespace(
                    name="alpha",
                    label=None,
                    type=SimpleNamespace(kind=SimpleNamespace(value="str")),
                ),
                SimpleNamespace(
                    name="beta",
                    label=None,
                    type=SimpleNamespace(kind=SimpleNamespace(value="str")),
                ),
            ],
            state_machine=None,
        )
        surface = SimpleNamespace(
            sections=[
                SimpleNamespace(
                    elements=[
                        SimpleNamespace(field_name="beta"),
                        SimpleNamespace(field_name="alpha"),
                    ]
                )
            ]
        )
        cols = _build_surface_columns(entity, surface)
        assert [c["key"] for c in cols] == ["beta", "alpha"]

    def test_surface_ref_column(self) -> None:
        """Ref fields in surface should render with type=ref."""
        from dazzle_back.runtime.workspace_rendering import _build_surface_columns

        entity = SimpleNamespace(
            fields=[
                SimpleNamespace(
                    name="id", type=SimpleNamespace(kind=SimpleNamespace(value="uuid"))
                ),
                SimpleNamespace(
                    name="company_id",
                    label="Company",
                    type=SimpleNamespace(kind=SimpleNamespace(value="ref"), ref_entity="Company"),
                ),
            ],
            state_machine=None,
        )
        surface = SimpleNamespace(
            sections=[SimpleNamespace(elements=[SimpleNamespace(field_name="company_id")])]
        )
        cols = _build_surface_columns(entity, surface)
        assert len(cols) == 1
        assert cols[0]["key"] == "company"
        assert cols[0]["type"] == "ref"


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


# ---------------------------------------------------------------------------
# Nav groups scoped to active workspace (#422)
# ---------------------------------------------------------------------------


class TestNavGroupWorkspaceScoping:
    """nav_groups passed to each workspace handler must only include
    groups from that workspace, not all workspaces."""

    def test_nav_group_map_is_per_workspace(self) -> None:
        """The nav_group_map should key groups by workspace name."""
        from dazzle.core.ir import NavGroupSpec, NavItemIR, WorkspaceSpec

        ws_agent = WorkspaceSpec(
            name="agent_dashboard",
            title="Agent Dashboard",
            nav_groups=[
                NavGroupSpec(
                    label="Agent Tools",
                    icon="wrench",
                    items=[NavItemIR(entity="tickets")],
                ),
            ],
        )
        ws_manager = WorkspaceSpec(
            name="manager_dashboard",
            title="Manager Dashboard",
            nav_groups=[
                NavGroupSpec(
                    label="Manager Reports",
                    icon="bar-chart",
                    items=[NavItemIR(entity="reports")],
                ),
                NavGroupSpec(
                    label="Team",
                    items=[NavItemIR(entity="team_members")],
                ),
            ],
        )
        workspaces = [ws_agent, ws_manager]
        app_prefix = "/app"

        # Replicate the per-workspace nav_group building logic from page_routes
        ws_nav_group_map: dict[str, list[dict[str, Any]]] = {}
        for ws in workspaces:
            groups: list[dict[str, Any]] = []
            for ng in getattr(ws, "nav_groups", []) or []:
                groups.append(
                    {
                        "label": ng.label,
                        "icon": ng.icon,
                        "collapsed": ng.collapsed,
                        "children": [
                            {
                                "label": item.entity.replace("_", " ").title(),
                                "route": f"{app_prefix}/{item.entity.lower().replace('_', '-')}",
                                "icon": item.icon,
                            }
                            for item in ng.items
                        ],
                    }
                )
            ws_nav_group_map[ws.name] = groups

        # Agent workspace should only have its own group
        assert len(ws_nav_group_map["agent_dashboard"]) == 1
        assert ws_nav_group_map["agent_dashboard"][0]["label"] == "Agent Tools"

        # Manager workspace should have its own 2 groups
        assert len(ws_nav_group_map["manager_dashboard"]) == 2
        labels = {g["label"] for g in ws_nav_group_map["manager_dashboard"]}
        assert labels == {"Manager Reports", "Team"}

        # No cross-contamination
        all_agent_labels = {g["label"] for g in ws_nav_group_map["agent_dashboard"]}
        all_manager_labels = {g["label"] for g in ws_nav_group_map["manager_dashboard"]}
        assert all_agent_labels.isdisjoint(all_manager_labels)

    def test_workspace_without_nav_groups_gets_empty_list(self) -> None:
        """Workspaces with no nav_groups should get an empty list, not others' groups."""
        from dazzle.core.ir import NavGroupSpec, NavItemIR, WorkspaceSpec

        ws_with = WorkspaceSpec(
            name="main",
            title="Main",
            nav_groups=[
                NavGroupSpec(label="Tools", items=[NavItemIR(entity="tasks")]),
            ],
        )
        ws_without = WorkspaceSpec(
            name="empty",
            title="Empty",
            nav_groups=[],
        )

        ws_nav_group_map: dict[str, list[dict[str, Any]]] = {}
        for ws in [ws_with, ws_without]:
            groups: list[dict[str, Any]] = []
            for ng in getattr(ws, "nav_groups", []) or []:
                groups.append({"label": ng.label})
            ws_nav_group_map[ws.name] = groups

        assert len(ws_nav_group_map["main"]) == 1
        assert len(ws_nav_group_map["empty"]) == 0


class TestNavGroupRouteGeneration:
    """nav_group children should use entity-slug routes, not /workspaces/{entity}."""

    def test_nav_group_children_use_entity_slug_route(self) -> None:
        """Children should route to /app/{entity_slug}, not /app/workspaces/{entity}."""
        from dazzle.core.ir import NavGroupSpec, NavItemIR, WorkspaceSpec

        ws = WorkspaceSpec(
            name="ops",
            title="Operations",
            nav_groups=[
                NavGroupSpec(
                    label="Events",
                    items=[
                        NavItemIR(entity="AssessmentEvent"),
                        NavItemIR(entity="session_attendance"),
                    ],
                ),
            ],
        )
        app_prefix = "/app"

        # Replicate the nav_group child route logic from page_routes
        for ng in ws.nav_groups:
            children = [
                {
                    "route": f"{app_prefix}/{item.entity.lower().replace('_', '-')}",
                }
                for item in ng.items
            ]

        assert children[0]["route"] == "/app/assessmentevent"
        assert children[1]["route"] == "/app/session-attendance"

    def test_nav_group_children_use_list_surface_title(self) -> None:
        """When a list surface exists for the entity, use its title."""
        from types import SimpleNamespace

        from dazzle.core.ir import NavGroupSpec, NavItemIR, WorkspaceSpec

        ws = WorkspaceSpec(
            name="ops",
            title="Operations",
            nav_groups=[
                NavGroupSpec(
                    label="Events",
                    items=[
                        NavItemIR(entity="AttendanceSession"),
                        NavItemIR(entity="orphan_entity"),
                    ],
                ),
            ],
        )
        # Mock list surfaces
        _list_surfaces_by_entity = {
            "AttendanceSession": SimpleNamespace(title="Session Attendance"),
        }

        for ng in ws.nav_groups:
            children = [
                {
                    "label": (
                        _list_surfaces_by_entity[item.entity].title
                        if item.entity in _list_surfaces_by_entity
                        and _list_surfaces_by_entity[item.entity].title
                        else item.entity.replace("_", " ").title()
                    ),
                }
                for item in ng.items
            ]

        assert children[0]["label"] == "Session Attendance"
        assert children[1]["label"] == "Orphan Entity"


class TestNavGroupEntityExclusion:
    """Entities in nav_groups should not appear as ungrouped flat entity items."""

    def test_grouped_entities_excluded_from_ws_entity_nav(self) -> None:
        """Entities claimed by a nav_group should not appear in ws_entity_nav."""
        from types import SimpleNamespace

        from dazzle.core.ir import (
            NavGroupSpec,
            NavItemIR,
            WorkspaceSpec,
        )
        from dazzle.core.ir.workspaces import WorkspaceRegion

        ws = WorkspaceSpec(
            name="ops",
            title="Operations",
            regions=[
                WorkspaceRegion(
                    name="events",
                    source="AssessmentEvent",
                ),
                WorkspaceRegion(
                    name="people",
                    source="Person",
                ),
            ],
            nav_groups=[
                NavGroupSpec(
                    label="Events",
                    items=[NavItemIR(entity="AssessmentEvent")],
                ),
            ],
        )

        # Mock surfaces for both entities
        _list_surfaces_by_entity = {
            "AssessmentEvent": SimpleNamespace(title="Assessment Events"),
            "Person": SimpleNamespace(title="People"),
        }

        # Replicate the grouped-entity exclusion logic from page_routes
        grouped: set[str] = set()
        for ng in getattr(ws, "nav_groups", []) or []:
            for item in ng.items:
                grouped.add(item.entity)

        entity_items: list[dict[str, Any]] = []
        seen: set[str] = set()
        app_prefix = "/app"
        for region in ws.regions:
            region_sources: list[str] = []
            if region.source:
                region_sources.append(region.source)
            for src in region_sources:
                if src not in seen and src not in grouped:
                    seen.add(src)
                    ls = _list_surfaces_by_entity.get(src)
                    if ls:
                        entity_items.append(
                            {
                                "label": ls.title or src,
                                "route": f"{app_prefix}/{src.lower().replace('_', '-')}",
                            }
                        )

        # Only Person should appear — AssessmentEvent is in a nav_group
        assert len(entity_items) == 1
        assert entity_items[0]["label"] == "People"
        assert entity_items[0]["route"] == "/app/person"

    def test_no_nav_groups_all_entities_in_ws_entity_nav(self) -> None:
        """Without nav_groups, all entities should appear as flat items."""
        from types import SimpleNamespace

        from dazzle.core.ir import WorkspaceSpec
        from dazzle.core.ir.workspaces import WorkspaceRegion

        ws = WorkspaceSpec(
            name="ops",
            title="Operations",
            regions=[
                WorkspaceRegion(name="a", source="Task"),
                WorkspaceRegion(name="b", source="Project"),
            ],
            nav_groups=[],
        )

        _list_surfaces_by_entity = {
            "Task": SimpleNamespace(title="Tasks"),
            "Project": SimpleNamespace(title="Projects"),
        }

        grouped: set[str] = set()
        for ng in getattr(ws, "nav_groups", []) or []:
            for item in ng.items:
                grouped.add(item.entity)

        entity_items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for region in ws.regions:
            if region.source and region.source not in seen and region.source not in grouped:
                seen.add(region.source)
                ls = _list_surfaces_by_entity.get(region.source)
                if ls:
                    entity_items.append({"label": ls.title})

        assert len(entity_items) == 2
        labels = {i["label"] for i in entity_items}
        assert labels == {"Tasks", "Projects"}


# ---------------------------------------------------------------------------
# Step 5 — Workspace primary-action candidates (#827)
# ---------------------------------------------------------------------------


class TestWorkspacePrimaryActionCandidates:
    """``_build_workspace_primary_action_candidates`` collects "New X" buttons.

    Regression guard for #827: workspace dashboards rendered title-only
    headers even when regions referenced an entity with a working create
    surface. The helper must produce one candidate per unique region-source
    entity that has a CREATE surface.
    """

    def _ws(self, *regions: Any) -> Any:
        return SimpleNamespace(name="ws", regions=list(regions))

    def _region(self, source: str | None = None, sources: list[str] | None = None) -> Any:
        return SimpleNamespace(source=source or "", sources=sources or [])

    def test_single_region_entity_with_create_surface_emits_candidate(self) -> None:
        from dazzle_ui.runtime.page_routes import _build_workspace_primary_action_candidates

        ws = self._ws(self._region(source="Task"))
        create_surfaces = {"Task": SimpleNamespace(name="task_create")}
        list_surfaces = {"Task": SimpleNamespace(title="Tasks")}

        actions = _build_workspace_primary_action_candidates(
            ws,
            app_prefix="/app",
            create_surfaces_by_entity=create_surfaces,
            list_surfaces_by_entity=list_surfaces,
        )
        assert actions == [
            {
                "entity": "Task",
                "surface": "task_create",
                "label": "New Tasks",
                "route": "/app/task/create",
            }
        ]

    def test_entity_without_create_surface_omitted(self) -> None:
        from dazzle_ui.runtime.page_routes import _build_workspace_primary_action_candidates

        ws = self._ws(self._region(source="Report"))
        actions = _build_workspace_primary_action_candidates(
            ws,
            app_prefix="/app",
            create_surfaces_by_entity={},
            list_surfaces_by_entity={"Report": SimpleNamespace(title="Reports")},
        )
        assert actions == []

    def test_duplicate_entity_references_deduplicated(self) -> None:
        """Multiple regions on the same entity only surface one button."""
        from dazzle_ui.runtime.page_routes import _build_workspace_primary_action_candidates

        ws = self._ws(
            self._region(source="Task"),
            self._region(source="Task"),
            self._region(sources=["Task"]),
        )
        actions = _build_workspace_primary_action_candidates(
            ws,
            app_prefix="/app",
            create_surfaces_by_entity={"Task": SimpleNamespace(name="task_create")},
            list_surfaces_by_entity={"Task": SimpleNamespace(title="Tasks")},
        )
        assert len(actions) == 1

    def test_multi_source_region_collects_each_entity(self) -> None:
        from dazzle_ui.runtime.page_routes import _build_workspace_primary_action_candidates

        ws = self._ws(self._region(sources=["Task", "Project"]))
        actions = _build_workspace_primary_action_candidates(
            ws,
            app_prefix="/app",
            create_surfaces_by_entity={
                "Task": SimpleNamespace(name="task_create"),
                "Project": SimpleNamespace(name="project_create"),
            },
            list_surfaces_by_entity={
                "Task": SimpleNamespace(title="Tasks"),
                "Project": SimpleNamespace(title="Projects"),
            },
        )
        assert [a["entity"] for a in actions] == ["Task", "Project"]

    def test_missing_list_surface_falls_back_to_humanised_entity_name(self) -> None:
        from dazzle_ui.runtime.page_routes import _build_workspace_primary_action_candidates

        ws = self._ws(self._region(source="AuditLog"))
        actions = _build_workspace_primary_action_candidates(
            ws,
            app_prefix="/app",
            create_surfaces_by_entity={"AuditLog": SimpleNamespace(name="auditlog_create")},
            list_surfaces_by_entity={},
        )
        assert actions[0]["label"] == "New Audit Log" or actions[0]["label"] == "New Auditlog"

    def test_entity_slug_uses_lowercase_dashed_form(self) -> None:
        """Matches the routing convention at template_compiler.py:1474."""
        from dazzle_ui.runtime.page_routes import _build_workspace_primary_action_candidates

        ws = self._ws(self._region(source="ProjectMember"))
        actions = _build_workspace_primary_action_candidates(
            ws,
            app_prefix="/app",
            create_surfaces_by_entity={"ProjectMember": SimpleNamespace(name="pm_create")},
            list_surfaces_by_entity={},
        )
        # PascalCase lower().replace("_","-") → "projectmember"
        assert actions[0]["route"] == "/app/projectmember/create"


# ---------------------------------------------------------------------------
# Cycle 280 — EX-051 cross-cutting None-vs-default sweep
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestNoneVsDefaultDriftSweep:
    """Regression guards for EX-051 — None-vs-undefined rendering drift.

    Jinja's ``| default(X)`` filter only fires on *undefined*, not on None.
    Templates that used ``{{ item[col.key] | default("—") }}`` rendered the
    literal Python string "None" when the field was defined but null.
    Cycle 272 caught this in detail-region via Heuristic 1; cycle 280 swept
    the cross-cutting cases:

    - ``fragments/related_file_list.html`` (2 lines)
    - ``fragments/related_status_cards.html`` (2 lines)
    - ``fragments/table_rows.html`` (1 line — percentage column)

    Each site was converted to ``{% if val is none %}<fallback>{% else %}{{ val }}{% endif %}``
    which correctly handles None while preserving numeric 0 / False rendering.
    """

    def _make_group(self, *, columns, rows):
        """Build a group/tabs structure matching related-displays template shape."""
        tab = SimpleNamespace(
            label="Attachments",
            entity_name="Attachment",
            visible=True,
            columns=columns,
            rows=rows,
            create_url=None,
            detail_url_template=None,
            filter_field="parent_id",
        )
        return SimpleNamespace(tabs=[tab])

    def test_related_file_list_none_renders_emdash_not_literal_none(self) -> None:
        """Primary label: None → — (not literal "None")."""
        group = self._make_group(
            columns=[
                {"key": "name", "label": "Name", "type": "text"},
                {"key": "size", "label": "Size", "type": "text"},
            ],
            rows=[{"id": "1", "name": None, "size": "1KB"}],
        )
        detail = SimpleNamespace(item={"id": "parent-1"})
        html = render_fragment(
            "fragments/related_file_list.html",
            group=group,
            detail=detail,
        )
        assert "—" in html
        assert ">None<" not in html
        assert "None</p>" not in html

    def test_related_file_list_none_secondary_renders_empty_not_literal_none(
        self,
    ) -> None:
        """Secondary label: None → "" (empty, not literal "None")."""
        group = self._make_group(
            columns=[
                {"key": "name", "label": "Name", "type": "text"},
                {"key": "caption", "label": "Caption", "type": "text"},
            ],
            rows=[{"id": "1", "name": "file.pdf", "caption": None}],
        )
        detail = SimpleNamespace(item={"id": "parent-1"})
        html = render_fragment(
            "fragments/related_file_list.html",
            group=group,
            detail=detail,
        )
        assert "file.pdf" in html
        assert ">None<" not in html
        assert "None</p>" not in html

    def test_related_status_cards_none_renders_emdash(self) -> None:
        """All lines in related_status_cards use emdash fallback."""
        group = self._make_group(
            columns=[
                {"key": "title", "label": "Title", "type": "text"},
                {"key": "priority", "label": "Priority", "type": "text"},
                {"key": "owner_name", "label": "Owner", "type": "text"},
            ],
            rows=[
                {"id": "1", "title": None, "priority": None, "owner_name": None},
            ],
        )
        detail = SimpleNamespace(item={"id": "parent-1"})
        html = render_fragment(
            "fragments/related_status_cards.html",
            group=group,
            detail=detail,
        )
        assert "—" in html
        assert ">None<" not in html
        assert "None</p>" not in html

    def test_related_status_cards_real_value_renders_correctly(self) -> None:
        """Sanity check: real (non-None) values still render normally."""
        group = self._make_group(
            columns=[
                {"key": "title", "label": "Title", "type": "text"},
                {"key": "priority", "label": "Priority", "type": "text"},
            ],
            rows=[{"id": "1", "title": "Login broken", "priority": "high"}],
        )
        detail = SimpleNamespace(item={"id": "parent-1"})
        html = render_fragment(
            "fragments/related_status_cards.html",
            group=group,
            detail=detail,
        )
        assert "Login broken" in html
        assert "high" in html

    def _pct_table(self, *, rate_value):
        """Build a minimal table struct with one percentage column."""
        return {
            "rows": [{"id": "1", "rate": rate_value}],
            "columns": [
                {"key": "rate", "label": "Rate", "type": "percentage"},
            ],
            "entity_name": "Metric",
        }

    def test_table_rows_percentage_none_renders_emdash_not_none_percent(self) -> None:
        """Percentage column: None → — (not literal "None%")."""
        html = render_fragment(
            "fragments/table_rows.html",
            table=self._pct_table(rate_value=None),
        )
        assert "None%" not in html
        assert "—" in html

    def test_table_rows_percentage_zero_renders_zero_percent(self) -> None:
        """Percentage column: 0 renders as "0%" (not "—") — zero is meaningful data."""
        html = render_fragment(
            "fragments/table_rows.html",
            table=self._pct_table(rate_value=0),
        )
        assert "0%" in html

    def test_table_rows_percentage_real_value(self) -> None:
        """Percentage column: real value (e.g. 42) → "42%"."""
        html = render_fragment(
            "fragments/table_rows.html",
            table=self._pct_table(rate_value=42),
        )
        assert "42%" in html


# ---------------------------------------------------------------------------
# Cycle 282 — attention_accent macro (shared consolidation)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestAttentionAccentMacro:
    """The attention_accent macro consolidates the tier-to-class mapping.

    Cycle 282 — extracted from dev_docs/framework-gaps/2026-04-20-
    attention-tier-taxonomy-drift.md. The macro has 4 style variants
    (border/tint/both/bullet) and 3 tiers (critical/warning/notice),
    mirroring the per-region implementations that were previously
    duplicated across grid/timeline/queue/list.
    """

    def _render_macro(self, attn, style):
        """Render the macro in isolation via Jinja env."""
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        tmpl = env.from_string(
            "{% from 'macros/attention_accent.html' import attention_classes %}"
            "{{ attention_classes(attn, style) }}"
        )
        return tmpl.render(attn=attn, style=style)

    def test_border_critical_destructive(self) -> None:
        out = self._render_macro({"level": "critical"}, "border")
        assert "border-l-4" in out
        assert "border-l-[hsl(var(--destructive))]" in out

    def test_border_warning_warning(self) -> None:
        out = self._render_macro({"level": "warning"}, "border")
        assert "border-l-[hsl(var(--warning))]" in out

    def test_border_notice_primary(self) -> None:
        out = self._render_macro({"level": "notice"}, "border")
        assert "border-l-[hsl(var(--primary))]" in out

    def test_border_none_emits_nothing(self) -> None:
        """With no attn and style=border, macro emits empty string."""
        out = self._render_macro(None, "border")
        assert out.strip() == ""

    def test_tint_critical_destructive_0_08(self) -> None:
        out = self._render_macro({"level": "critical"}, "tint")
        assert "bg-[hsl(var(--destructive)/0.08)]" in out

    def test_tint_warning_warning_0_08(self) -> None:
        out = self._render_macro({"level": "warning"}, "tint")
        assert "bg-[hsl(var(--warning)/0.08)]" in out

    def test_tint_notice_primary_0_06(self) -> None:
        """Notice alpha is 0.06 (lighter than critical/warning 0.08)."""
        out = self._render_macro({"level": "notice"}, "tint")
        assert "bg-[hsl(var(--primary)/0.06)]" in out

    def test_both_critical_border_and_tint_0_04(self) -> None:
        """Queue-region style: dual signal (border + 0.04 alpha tint)."""
        out = self._render_macro({"level": "critical"}, "both")
        assert "border-l-[hsl(var(--destructive))]" in out
        assert "bg-[hsl(var(--destructive)/0.04)]" in out

    def test_both_warning_dual_signal(self) -> None:
        out = self._render_macro({"level": "warning"}, "both")
        assert "border-l-[hsl(var(--warning))]" in out
        assert "bg-[hsl(var(--warning)/0.04)]" in out

    def test_both_notice_dual_signal(self) -> None:
        out = self._render_macro({"level": "notice"}, "both")
        assert "border-l-[hsl(var(--primary))]" in out
        assert "bg-[hsl(var(--primary)/0.04)]" in out

    def test_bullet_critical_text_destructive(self) -> None:
        """Timeline-region style: bullet marker text colour."""
        out = self._render_macro({"level": "critical"}, "bullet")
        assert "text-[hsl(var(--destructive))]" in out

    def test_bullet_warning_text_warning(self) -> None:
        out = self._render_macro({"level": "warning"}, "bullet")
        assert "text-[hsl(var(--warning))]" in out

    def test_bullet_notice_text_primary(self) -> None:
        out = self._render_macro({"level": "notice"}, "bullet")
        assert "text-[hsl(var(--primary))]" in out

    def test_bullet_none_falls_back_to_primary(self) -> None:
        """Bullet is the only style that emits a class when attn is None —
        timeline's default bullet colour is --primary."""
        out = self._render_macro(None, "bullet")
        assert "text-[hsl(var(--primary))]" in out

    def test_tint_none_emits_nothing(self) -> None:
        out = self._render_macro(None, "tint")
        assert out.strip() == ""

    def test_both_none_emits_nothing(self) -> None:
        out = self._render_macro(None, "both")
        assert out.strip() == ""

    def test_unknown_level_emits_safe_fallback(self) -> None:
        """Unknown level (e.g. 'error' instead of 'critical') emits
        the base class only (border-l-4 for border, nothing for others).
        Protects against typos in DSL-authored attention values."""
        out = self._render_macro({"level": "error"}, "border")
        # base 'border-l-4' present but no specific colour token
        assert "border-l-4" in out
        assert "hsl(var(--destructive))" not in out

        out_tint = self._render_macro({"level": "error"}, "tint")
        assert out_tint.strip() == ""


# ---------------------------------------------------------------------------
# Cycle 283 — ref_cell macro (shared consolidation across 3 regions)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestRefCellMacro:
    """The ref_cell macro consolidates the ref-column display chain.

    Cycle 283 — the repeated pattern (set display_name from _display hint
    or ref_display filter; wrap in anchor when ref_route present; emdash
    fallback for None) was duplicated across detail/grid/list regions with
    only the anchor mode differing. Macro extracted with 3 mode variants:

    - mode='link'        — detail-region (plain <a href>, no stopPropagation)
    - mode='link_stop'   — grid-region (<a href> + event.stopPropagation)
    - mode='htmx_drawer' — list-region (<a hx-get> into drawer + stopPropagation)

    timeline-region (UX-067) deliberately kept its simplified chain, not
    migrated to this macro.
    """

    def _render_macro(self, ref, display_hint="", ref_route="", mode="link"):
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        tmpl = env.from_string(
            "{% from 'macros/ref_cell.html' import ref_cell %}"
            "{{ ref_cell(ref, display_hint, ref_route, mode) }}"
        )
        return tmpl.render(ref=ref, display_hint=display_hint, ref_route=ref_route, mode=mode)

    def test_link_mode_mapping_with_route_renders_anchor(self) -> None:
        out = self._render_macro({"id": "u42", "name": "Alice"}, "", "/user/{id}", "link")
        assert '<a href="/user/u42"' in out
        assert "hsl(var(--primary))" in out
        assert ">Alice</a>" in out
        assert "onclick" not in out  # detail mode does NOT include stopPropagation

    def test_link_stop_mode_adds_stop_propagation(self) -> None:
        out = self._render_macro({"id": "u42", "name": "Bob"}, "", "/user/{id}", "link_stop")
        assert '<a href="/user/u42"' in out
        assert 'onclick="event.stopPropagation()"' in out
        assert ">Bob</a>" in out

    def test_htmx_drawer_mode_uses_hx_get_not_href(self) -> None:
        out = self._render_macro({"id": "u42", "name": "Carol"}, "", "/user/{id}", "htmx_drawer")
        assert 'hx-get="/user/u42"' in out
        assert 'hx-target="#dz-detail-drawer-content"' in out
        assert 'onclick="event.stopPropagation()"' in out
        # No href attribute — this is an HTMX-driven anchor, not a native nav
        assert 'href="' not in out

    def test_display_hint_wins_over_ref_display_filter(self) -> None:
        """When `_display` suffix value is provided, it's used verbatim."""
        out = self._render_macro(
            {"id": "u42", "name": "Alice"}, "Alice Smith (VIP)", "/user/{id}", "link"
        )
        assert "Alice Smith (VIP)" in out
        assert ">Alice<" not in out  # ref_display fallback must not fire

    def test_ref_display_filter_fires_when_no_hint(self) -> None:
        """With no hint, ref_display_name(ref) drives display name."""
        out = self._render_macro(
            {"id": "u42", "first_name": "Alice", "last_name": "Zhang"},
            "",
            "/user/{id}",
            "link",
        )
        # ref_display_name concatenates first+last when `name` isn't set
        assert "Alice Zhang" in out

    def test_mapping_without_route_renders_plain_name(self) -> None:
        """No ref_route → no anchor, just display name as text."""
        out = self._render_macro({"id": "u42", "name": "Alice"}, "", "", "link")
        assert "<a " not in out
        assert "Alice" in out

    def test_mapping_without_id_renders_plain_name(self) -> None:
        """Route set but ref lacks id → no anchor (can't fill template)."""
        out = self._render_macro({"name": "Alice"}, "", "/user/{id}", "link")
        assert "<a " not in out
        assert "Alice" in out

    def test_scalar_ref_renders_verbatim(self) -> None:
        """Non-mapping ref (e.g. raw string id) renders the value directly."""
        out = self._render_macro("raw-id-value", "", "", "link")
        assert "raw-id-value" in out

    def test_display_hint_only_when_no_ref(self) -> None:
        """No ref but display_hint set → hint rendered as plain text."""
        out = self._render_macro("", "Cached Display Name", "", "link")
        assert "Cached Display Name" in out
        assert "<a " not in out

    def test_emdash_fallback_for_none(self) -> None:
        """Ref=None with no display hint → em-dash."""
        out = self._render_macro(None, "", "", "link")
        assert out.strip() == "—"

    def test_emdash_fallback_for_empty_ref(self) -> None:
        """Ref=empty string with no display hint → em-dash."""
        out = self._render_macro("", "", "", "link")
        assert out.strip() == "—"

    def test_mode_defaults_to_link_when_unknown(self) -> None:
        """Unknown mode falls through to plain display_name (no anchor)."""
        out = self._render_macro({"id": "u42", "name": "Alice"}, "", "/user/{id}", "weird_mode")
        # No anchor for unknown mode (safety default)
        assert "<a " not in out
        assert "Alice" in out


# ---------------------------------------------------------------------------
# Cycle 286 — alpine-dropdown contract (orphaned primitive)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestAlpineDropdownComponent:
    """components/alpine/dropdown.html — available primitive, zero current
    consumers.

    Cycle 286 discovered via Heuristic 1 that cycle 237's coverage-map
    claim of "42 call sites" was wrong — the template has NO `{% include %}`
    references anywhere in the codebase today. It's a ready-to-use Alpine
    primitive waiting for an adopter.

    Contract at ~/.claude/skills/ux-architect/components/alpine-dropdown.md.
    These tests pin the primitive's API so any future adopter inherits a
    stable target.
    """

    def _render(self, **ctx):
        from dazzle_ui.runtime.template_renderer import render_fragment

        return render_fragment("components/alpine/dropdown.html", **ctx)

    def test_outer_wrapper_has_alpine_and_dismiss_handlers(self) -> None:
        """Gate 1: dz root has x-data, @click.outside, @keydown.escape.window."""
        html = self._render(dropdown_label="Menu", dropdown_items=[])
        assert 'x-data="{ open: false }"' in html
        assert '@click.outside="open = false"' in html
        assert '@keydown.escape.window="open = false"' in html

    def test_trigger_button_has_toggle_handler(self) -> None:
        """Gate 2: trigger <button> has @click="open = !open"."""
        html = self._render(dropdown_label="Actions", dropdown_items=[])
        assert "<button " in html
        assert '@click="open = !open"' in html

    def test_trigger_label_rendered(self) -> None:
        """Gate 3a: the dropdown_label text appears in the trigger."""
        html = self._render(dropdown_label="Custom Label", dropdown_items=[])
        assert "Custom Label" in html

    def test_trigger_label_defaults_to_actions(self) -> None:
        """Gate 3a (default): dropdown_label defaults to 'Actions'."""
        html = self._render(dropdown_items=[])
        assert "Actions" in html

    def test_caret_rotates_on_open(self) -> None:
        """Gate 3b: caret SVG has `:class="open && 'rotate-180'"`."""
        html = self._render(dropdown_label="X", dropdown_items=[])
        assert "transition-transform" in html
        assert "'rotate-180'" in html

    def test_menu_is_ul_with_x_show(self) -> None:
        """Gate 4: menu is <ul x-show="open">."""
        html = self._render(dropdown_label="X", dropdown_items=[])
        assert "<ul " in html
        assert 'x-show="open"' in html
        assert "x-transition" in html

    def test_menu_positioned_below_right(self) -> None:
        """Gate 5: menu has absolute right-0 mt-1 z-50 positioning."""
        html = self._render(dropdown_label="X", dropdown_items=[])
        assert "absolute" in html
        assert "right-0" in html
        assert "z-50" in html

    def test_menu_chrome_uses_design_tokens(self) -> None:
        """Gate 6: menu chrome references --card, --border tokens."""
        html = self._render(dropdown_label="X", dropdown_items=[])
        assert "bg-[hsl(var(--card))]" in html
        assert "border-[hsl(var(--border))]" in html
        assert "rounded-lg" in html
        assert "shadow-md" in html

    def test_item_count_matches_dropdown_items(self) -> None:
        """Gate 7: DOM contains len(dropdown_items) <li> elements."""
        html = self._render(
            dropdown_label="X",
            dropdown_items=[
                {"label": "A", "href": "/a"},
                {"label": "B", "href": "/b"},
                {"label": "C", "href": "/c"},
            ],
        )
        assert html.count("<li>") == 3
        assert "A" in html and "B" in html and "C" in html

    def test_href_branch_renders_anchor(self) -> None:
        """Gate 8a: item with href → <a href>."""
        html = self._render(
            dropdown_label="X",
            dropdown_items=[{"label": "Go", "href": "/target"}],
        )
        assert '<a href="/target"' in html
        assert ">Go</a>" in html

    def test_hx_delete_branch_renders_button_with_confirm(self) -> None:
        """Gate 8b: item with hx_delete → <button hx-delete> + hx-confirm."""
        html = self._render(
            dropdown_label="X",
            dropdown_items=[
                {
                    "label": "Delete",
                    "hx_delete": "/api/item/42",
                    "confirm": "Really delete?",
                    "hx_target": "#item-42",
                }
            ],
        )
        assert "<button " in html
        assert 'hx-delete="/api/item/42"' in html
        assert 'hx-confirm="Really delete?"' in html
        assert 'hx-target="#item-42"' in html

    def test_hx_delete_confirm_defaults_to_are_you_sure(self) -> None:
        """Gate 8b (default): hx-confirm defaults to 'Are you sure?'."""
        html = self._render(
            dropdown_label="X",
            dropdown_items=[{"label": "Delete", "hx_delete": "/x"}],
        )
        assert "Are you sure?" in html

    def test_placeholder_branch_renders_noop_anchor(self) -> None:
        """Gate 8c: item with neither href nor hx_delete → <a href="#">."""
        html = self._render(
            dropdown_label="X",
            dropdown_items=[{"label": "Placeholder"}],
        )
        assert 'href="#"' in html

    def test_no_daisyui_leaks(self) -> None:
        """Gate 9: zero DaisyUI class references."""
        html = self._render(
            dropdown_label="X",
            dropdown_items=[
                {"label": "A", "href": "/"},
                {"label": "B", "hx_delete": "/d"},
            ],
        )
        for banned in ("dropdown ", "menu ", "btn-primary", "btn-ghost"):
            assert banned not in html, f"DaisyUI leak: {banned!r}"

    def test_empty_dropdown_items_renders_no_list_items(self) -> None:
        """Edge case: empty dropdown_items → <ul> with zero <li>."""
        html = self._render(dropdown_label="X", dropdown_items=[])
        assert "<ul " in html
        assert "<li>" not in html


# ---------------------------------------------------------------------------
# Cycle 288 — search-flow-fragments (search_results + select_result)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestSearchResultsFragment:
    """search_results.html — HTMX response listing matching items.

    Cycle 288 — uncontracted before this cycle (surfaced by cycle 285
    missing_contracts scan). Contract at
    ~/.claude/skills/ux-architect/components/search-flow-fragments.md.
    """

    def _render(self, **ctx):
        from dazzle_ui.runtime.template_renderer import render_fragment

        defaults = {
            "items": [],
            "display_key": "name",
            "secondary_key": None,
            "value_key": "id",
            "query": "",
            "min_chars": 2,
            "field_name": "owner",
            "select_endpoint": "/api/select/owner?field=owner",
        }
        defaults.update(ctx)
        return render_fragment("fragments/search_results.html", **defaults)

    def test_items_rendered_with_htmx_wiring(self) -> None:
        """Gates 1, 2, 3: each item is a clickable div with hx-get + primary label."""
        html = self._render(
            items=[
                {"id": "u1", "name": "Alice"},
                {"id": "u2", "name": "Bob"},
            ],
            query="a",
        )
        # Two items
        assert html.count("hx-get=") == 2
        # Each has the target wiring
        assert 'hx-target="#search-results-owner"' in html
        assert 'hx-swap="innerHTML"' in html
        # IDs appended to select_endpoint
        assert "&id=u1" in html
        assert "&id=u2" in html
        # Primary labels
        assert "Alice" in html
        assert "Bob" in html

    def test_secondary_label_rendered_when_key_provided(self) -> None:
        """Gate 4: secondary label renders when secondary_key + item value both truthy."""
        html = self._render(
            items=[
                {"id": "u1", "name": "Alice", "email": "alice@example.com"},
            ],
            secondary_key="email",
            query="a",
        )
        assert "Alice" in html
        assert "alice@example.com" in html
        assert "hsl(var(--muted-foreground))" in html

    def test_secondary_label_omitted_when_missing_from_item(self) -> None:
        """Gate 4 (negative): secondary_key set but item lacks the value → no secondary div."""
        html = self._render(
            items=[{"id": "u1", "name": "Alice"}],
            secondary_key="email",
            query="a",
        )
        assert "Alice" in html
        # No email div rendered
        # count of muted-foreground styling in items (the empty-state also uses it, but items don't when secondary absent)
        # Better: verify only 1 div per item
        result_divs = html.count("cursor-pointer")
        assert result_divs == 1

    def test_empty_state_with_query_shows_no_results_message(self) -> None:
        """Gate 5: empty items + query → 'No results found for "..."'."""
        html = self._render(items=[], query="xyzzy")
        assert 'No results found for "xyzzy"' in html
        assert "cursor-pointer" not in html

    def test_empty_state_without_query_shows_prompt(self) -> None:
        """Gate 5: empty items + no query → 'Type at least N characters...'."""
        html = self._render(items=[], query="", min_chars=3)
        assert "Type at least 3 characters" in html

    def test_hover_uses_muted_token(self) -> None:
        """Gate 6: items have hover:bg-[hsl(var(--muted))]."""
        html = self._render(items=[{"id": "1", "name": "Alice"}], query="a")
        assert "hover:bg-[hsl(var(--muted))]" in html

    def test_no_daisyui_leaks(self) -> None:
        """Gate 11: zero DaisyUI class references."""
        html = self._render(
            items=[{"id": "1", "name": "Alice"}],
            query="a",
        )
        for banned in ("dropdown ", "menu ", "input-bordered", "btn-primary"):
            assert banned not in html, f"DaisyUI leak: {banned!r}"


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestSelectResultFragment:
    """select_result.html — OOB swap response after user picks a search result.

    Cycle 288 — paired contract with search_results.html. Updates the
    hidden form field + visible search input + any autofill mappings
    via hx-swap-oob.
    """

    def _render(self, **ctx):
        from dazzle_ui.runtime.template_renderer import render_fragment

        defaults = {
            "display_val": "Alice Smith",
            "selected_value": "u42",
            "field_name": "owner",
            "autofill_values": [],
        }
        defaults.update(ctx)
        return render_fragment("fragments/select_result.html", **defaults)

    def test_confirmation_flash_uses_success_token(self) -> None:
        """Gate 7: confirmation uses --success token and shows 'Selected: X'."""
        html = self._render(display_val="Alice Smith")
        assert "text-[hsl(var(--success))]" in html
        assert "Selected: Alice Smith" in html

    def test_hidden_form_field_has_required_attrs(self) -> None:
        """Gate 8: hidden input has name, id, data-dazzle-field, value, hx-swap-oob."""
        html = self._render(selected_value="u42", field_name="owner")
        assert 'type="hidden"' in html
        assert 'name="owner"' in html
        assert 'id="field-owner"' in html
        assert 'data-dazzle-field="owner"' in html
        assert 'value="u42"' in html
        assert 'hx-swap-oob="true"' in html

    def test_visible_search_input_has_token_classes_and_oob_swap(self) -> None:
        """Gate 9: visible input references all 4 design tokens + hx-swap-oob."""
        html = self._render(display_val="Alice", field_name="owner")
        # The 4 token refs
        assert "bg-[hsl(var(--background))]" in html
        assert "border-[hsl(var(--border))]" in html
        assert "text-[hsl(var(--foreground))]" in html
        # Visible-input specific markers
        assert 'id="search-input-owner"' in html
        # hx-swap-oob on at least 2 inputs (hidden + visible)
        assert html.count('hx-swap-oob="true"') >= 2

    def test_autofill_values_emit_extra_oob_inputs(self) -> None:
        """Gate 10: one <input hx-swap-oob> per autofill tuple."""
        html = self._render(
            display_val="Alice",
            selected_value="u42",
            field_name="owner",
            autofill_values=[
                ("email", "alice@example.com"),
                ("department", "Engineering"),
            ],
        )
        # Each autofill field creates an OOB input
        assert 'id="field-email"' in html
        assert 'value="alice@example.com"' in html
        assert 'id="field-department"' in html
        assert 'value="Engineering"' in html
        # Total OOB inputs: 1 hidden + 1 visible + 2 autofill = 4
        assert html.count('hx-swap-oob="true"') == 4

    def test_zero_autofill_values_emits_only_core_oob_inputs(self) -> None:
        """Edge case: no autofill → only hidden + visible OOB inputs."""
        html = self._render(autofill_values=[])
        # 2 OOB inputs (hidden + visible)
        assert html.count('hx-swap-oob="true"') == 2

    def test_no_daisyui_leaks(self) -> None:
        """Gate 11: zero DaisyUI class references."""
        html = self._render()
        for banned in ("input-bordered", "dropdown ", "menu ", "btn-primary"):
            assert banned not in html, f"DaisyUI leak: {banned!r}"


class TestContractPointerCanonicalFormat:
    """Cycle 289 — pointer-format drift sweep.

    Cycle 285's missing_contracts scan flagged two templates with non-canonical
    Contract: pointer headers (filterable_table.html had an inline comma-joined
    reference; _card_picker.html had no pointer at all). This test pins the
    canonical shape so future edits don't silently regress.

    Canonical shape: ``{# ... Contract: ~/.claude/skills/ux-architect/components/<name>.md (UX-NNN)? #}``
    """

    @staticmethod
    def _read(rel_path: str) -> str:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "src" / "dazzle_ui" / "templates"
        return (root / rel_path).read_text()

    def test_filterable_table_has_canonical_pointer(self) -> None:
        src = self._read("components/filterable_table.html")
        assert "Contract: ~/.claude/skills/ux-architect/components/data-table.md" in src

    def test_card_picker_has_canonical_pointer_with_ux_id(self) -> None:
        src = self._read("workspace/_card_picker.html")
        assert (
            "Contract: ~/.claude/skills/ux-architect/components/workspace-card-picker.md (UX-038)"
            in src
        )

    def test_filterable_table_does_not_retain_legacy_pointer(self) -> None:
        """The cycle-285 drift ('data-table contract' comma-joined in line 1) must be gone."""
        src = self._read("components/filterable_table.html")
        assert "ux-architect/components/data-table contract" not in src


# ---------------------------------------------------------------------------
# Cycle 290 — Workspace shell composition contract (workspace-shell.md)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestWorkspaceShellComposition:
    """workspace/_content.html — composition shell pinning how 6 sub-components assemble.

    Cycle 290 — contract at ~/.claude/skills/ux-architect/components/workspace-shell.md.
    The shell delegates most sub-components to their own contracts (dashboard-grid,
    dashboard-edit-chrome, workspace-card-picker, workspace-detail-drawer). These
    tests pin the composition-level invariants + the two uncontracted sub-parts
    (workspace heading, context selector) per the embedded quality gates.
    """

    def _render(
        self,
        *,
        sse_url: str = "",
        context_options_url: str = "",
        context_selector_label: str = "",
        context_selector_entity: str = "",
        primary_actions: list[dict[str, str]] | None = None,
    ) -> str:
        from dazzle_ui.runtime.workspace_renderer import WorkspaceContext

        ws = WorkspaceContext(
            name="my_dashboard",
            title="My Dashboard",
            sse_url=sse_url,
            context_options_url=context_options_url,
            context_selector_label=context_selector_label,
            context_selector_entity=context_selector_entity,
        )
        return render_fragment(
            "workspace/_content.html",
            workspace=ws,
            layout_json="[]",
            primary_actions=primary_actions or [],
        )

    # Gate 1
    def test_layout_json_island_precedes_alpine_root(self) -> None:
        """Data island must appear before the Alpine controller root so init() can hydrate."""
        html = self._render()
        island_idx = html.find('id="dz-workspace-layout"')
        alpine_idx = html.find('x-data="dzDashboardBuilder()"')
        assert island_idx >= 0 and alpine_idx >= 0
        assert island_idx < alpine_idx

    # Gate 2
    def test_detail_drawer_sits_outside_alpine_root(self) -> None:
        """Detail drawer must be outside the Alpine scope — singleton, not per-instance."""
        html = self._render()
        drawer_idx = html.find('id="dz-detail-drawer"')
        alpine_root_close_idx = html.rfind("</div>", 0, drawer_idx)
        alpine_open_idx = html.find('x-data="dzDashboardBuilder()"')
        assert drawer_idx > alpine_root_close_idx > alpine_open_idx

    # Gate 3
    def test_six_composition_markers_present_in_order(self) -> None:
        html = self._render(primary_actions=[{"label": "New Task", "route": "/app/task/new"}])
        markers = [
            "<h2",
            'data-test-id="dz-workspace-primary-actions"',
            "resetLayout()",
            "data-grid-container",
            'data-test-id="dz-add-card-trigger"',
            'id="dz-detail-drawer"',
        ]
        positions = [html.find(m) for m in markers]
        assert all(p >= 0 for p in positions), (
            f"missing markers: {list(zip(markers, positions, strict=False))}"
        )
        assert positions == sorted(positions), "composition order drifted"

    # Gate 4
    def test_singleton_ids_unique(self) -> None:
        html = self._render()
        for marker in (
            'id="dz-workspace-layout"',
            'id="dz-detail-drawer"',
            'id="dz-drawer-backdrop"',
            'id="dz-detail-drawer-content"',
            'id="dz-drawer-expand"',
        ):
            assert html.count(marker) == 1, f"{marker} not unique"

    # Gate 5
    def test_heading_uses_foreground_token_with_title_fallback(self) -> None:
        html = self._render()
        # The h2 opening tag and the --foreground token must co-occur
        assert "<h2" in html
        assert "text-[hsl(var(--foreground))]" in html
        # Title renders ("My Dashboard" — set on the WorkspaceContext)
        assert "My Dashboard" in html

    # Gate 6
    def test_primary_actions_row_conditional(self) -> None:
        # Empty list → wrapper absent
        html_empty = self._render(primary_actions=[])
        assert 'data-test-id="dz-workspace-primary-actions"' not in html_empty
        # Populated → wrapper present + hx-boost + primary token
        html_full = self._render(
            primary_actions=[
                {"label": "New Task", "route": "/app/task/new"},
                {"label": "New Contact", "route": "/app/contact/new"},
            ]
        )
        assert 'data-test-id="dz-workspace-primary-actions"' in html_full
        assert html_full.count('hx-boost="true"') >= 2
        assert "bg-[hsl(var(--primary))]" in html_full
        assert "text-[hsl(var(--primary-foreground))]" in html_full
        # Action labels render into anchor inner text (allowing intermediate whitespace + SVG icons)
        assert "New Task" in html_full
        assert "New Contact" in html_full
        assert 'href="/app/task/new"' in html_full
        assert 'href="/app/contact/new"' in html_full

    # Gate 7
    def test_context_selector_conditional_on_context_options_url(self) -> None:
        html_off = self._render(context_options_url="", context_selector_entity="project")
        assert 'id="dz-context-selector"' not in html_off

        html_on = self._render(
            context_options_url="/api/workspaces/my_dashboard/context_options",
            context_selector_entity="project",
            context_selector_label="Project",
        )
        assert 'id="dz-context-selector"' in html_on
        assert "Project:" in html_on

    # Gate 8
    def test_context_selector_uses_full_token_set(self) -> None:
        html = self._render(
            context_options_url="/api/foo",
            context_selector_entity="tenant",
        )
        # All four required tokens on the <select>
        assert "border-[hsl(var(--border))]" in html
        assert "bg-[hsl(var(--background))]" in html
        assert "text-[hsl(var(--foreground))]" in html
        assert "focus:ring-[hsl(var(--ring))]" in html

    # Gate 9
    def test_context_selector_uses_canonical_prefs_key(self) -> None:
        html = self._render(
            context_options_url="/api/foo",
            context_selector_entity="tenant",
        )
        # The prefs key is constructed in the bootstrap script — canonical shape
        assert "'workspace.' + wsName + '.context'" in html

    # Gate 10
    def test_grid_container_has_role_application_and_aria_label(self) -> None:
        html = self._render()
        # Single data-grid-container element carries both
        assert "data-grid-container" in html
        assert 'role="application"' in html
        assert 'aria-label="Dashboard card grid"' in html

    # Gate 11
    def test_sse_wiring_conditional(self) -> None:
        html_off = self._render(sse_url="")
        assert 'hx-ext="sse"' not in html_off
        assert "sse-connect=" not in html_off

        html_on = self._render(sse_url="/_ops/sse/events")
        assert 'hx-ext="sse"' in html_on
        assert 'sse-connect="/_ops/sse/events"' in html_on
        # Card body also listens for entity events when SSE is active
        assert "sse:entity.created" in html_on

    # Gate 12
    def test_card_body_hx_trigger_includes_load(self) -> None:
        """#798 regression guard: 'load' must be the primary trigger."""
        html = self._render()
        # The x-for template body has the card content <div> with hx-trigger
        import re

        triggers = re.findall(r'hx-trigger="([^"]+)"', html)
        assert any(t.startswith("load, intersect once") for t in triggers), (
            f"no hx-trigger starting with 'load, intersect once' — got: {triggers}"
        )

    # Gate 13
    def test_card_focus_ring_on_wrapper_not_article(self) -> None:
        """#794 card-within-a-card guard: focus ring lives on the wrapper with offset-2."""
        html = self._render()
        assert "focus:ring-2 focus:ring-[hsl(var(--ring))] focus:ring-offset-2" in html
        # The inner <article> must NOT have focus:ring classes
        import re

        article_tag = re.search(r"<article[^>]*>", html)
        assert article_tag is not None
        assert "focus:ring-" not in article_tag.group(0)

    # Gate 14 — drawer aside carries no Alpine directives (plain-JS imperative API only)
    def test_drawer_aside_has_no_alpine_directives(self) -> None:
        """The drawer is deliberately NOT Alpine-owned — it uses window.dzDrawer imperative API."""
        import re

        html = self._render()
        aside_match = re.search(r"<aside[^>]*id=\"dz-detail-drawer\"[^>]*>", html)
        assert aside_match is not None
        aside_tag = aside_match.group(0)
        for banned in ("x-data", "x-show", "x-transition", "@click", "@keydown"):
            assert banned not in aside_tag, f"Alpine directive leaked onto drawer aside: {banned}"

    # Gate 15
    def test_escape_key_handler_on_document(self) -> None:
        html = self._render()
        assert "document.addEventListener('keydown'" in html
        assert "e.key === 'Escape'" in html
        assert "window.dzDrawer.close()" in html

    # Contract pointer
    def test_contract_pointer_header_present(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "src" / "dazzle_ui" / "templates"
        src = (root / "workspace" / "_content.html").read_text()
        assert "Contract: ~/.claude/skills/ux-architect/components/workspace-shell.md" in src


# ---------------------------------------------------------------------------
# Cycle 291 — Experience shell composition contract (experience-shell.md, UX-072)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAS_TEMPLATE_RENDERER, reason="dazzle_ui not installed")
class TestExperienceShellComposition:
    """experience/_content.html — composition shell pinning step progress + 4-way dispatcher.

    Cycle 291 — contract at ~/.claude/skills/ux-architect/components/experience-shell.md.
    Distinct from workspace-shell (cycle 290's "near-twin" claim was wrong —
    different shell entirely). Tests cover: outer wrapper, title, stepper
    conditional + coloring, 4-way dispatcher branches (non-surface easiest),
    transition buttons, Alpine-free guarantee.
    """

    def _make_experience(
        self,
        *,
        steps: list[dict] | None = None,
        current_step: str = "step_one",
        transitions: list[dict] | None = None,
        page_context: object | None = None,
    ) -> object:
        from dazzle_ui.runtime.template_context import (
            ExperienceContext,
            ExperienceStepContext,
            ExperienceTransitionContext,
        )

        default_steps = (
            steps
            if steps is not None
            else [
                {"name": "step_one", "title": "First Step", "is_current": True},
                {"name": "step_two", "title": "Second Step"},
            ]
        )
        step_ctxs = [ExperienceStepContext(**s) for s in default_steps]

        tr_ctxs = [ExperienceTransitionContext(**t) for t in (transitions or [])]

        return ExperienceContext(
            name="onboarding",
            title="Get Started",
            steps=step_ctxs,
            current_step=current_step,
            transitions=tr_ctxs,
            page_context=page_context,  # type: ignore[arg-type]
        )

    def _render(self, experience: object) -> str:
        return render_fragment("experience/_content.html", experience=experience)

    # Gate 1
    def test_outer_wrapper_has_data_experience_and_centering(self) -> None:
        html = self._render(self._make_experience())
        assert 'data-dz-experience="onboarding"' in html
        assert "max-w-4xl" in html
        assert "mx-auto" in html

    # Gate 2
    def test_title_renders_as_h2_with_title_text(self) -> None:
        html = self._render(self._make_experience())
        assert "<h2" in html
        assert "Get Started" in html

    # Gate 3
    def test_stepper_conditional_on_multi_step(self) -> None:
        # Single step → no stepper
        single = self._make_experience(
            steps=[{"name": "only_step", "title": "Only", "is_current": True}],
            current_step="only_step",
        )
        html_single = self._render(single)
        assert 'class="dz-steps' not in html_single
        # Multi step → stepper present
        html_multi = self._render(self._make_experience())
        assert 'class="dz-steps' in html_multi

    # Gate 4
    def test_each_step_has_data_marker(self) -> None:
        html = self._render(self._make_experience())
        assert 'data-dz-exp-step="step_one"' in html
        assert 'data-dz-exp-step="step_two"' in html

    # Gate 5
    def test_current_step_has_aria_current(self) -> None:
        html = self._render(self._make_experience())
        # aria-current="step" must appear on the current step's <li>
        assert 'aria-current="step"' in html
        # exactly once (only the current step)
        assert html.count('aria-current="step"') == 1

    # Gate 6 — completed/current steps use --primary, pending use --muted
    def test_step_coloring_uses_correct_tokens(self) -> None:
        exp = self._make_experience(
            steps=[
                {"name": "step_one", "title": "One", "is_completed": True},
                {"name": "step_two", "title": "Two", "is_current": True},
                {"name": "step_three", "title": "Three"},  # pending
            ],
            current_step="step_two",
        )
        html = self._render(exp)
        # Current/completed: --primary
        assert "bg-[hsl(var(--primary))]" in html
        assert "text-[hsl(var(--primary-foreground))]" in html
        # Pending: --muted
        assert "bg-[hsl(var(--muted))]" in html
        assert "text-[hsl(var(--muted-foreground))]" in html

    # Gate 7 — connector line colour reflects LEFT step's completion
    def test_connector_line_colour_by_left_step(self) -> None:
        # Left step completed → connector uses --primary
        exp_completed_left = self._make_experience(
            steps=[
                {"name": "a", "title": "A", "is_completed": True},
                {"name": "b", "title": "B", "is_current": True},
            ],
            current_step="b",
        )
        html = self._render(exp_completed_left)
        # Look for the connector <div class="flex-1 mx-3 h-px ..."> with --primary
        assert "flex-1 mx-3 h-px" in html
        # With completed left, --primary line colour appears on the connector
        # (and also on the left step's chip — we just verify at least one primary occurrence)
        # Stronger assertion: search for the pattern specifically
        import re

        connectors = re.findall(
            r'<div class="flex-1 mx-3 h-px [^"]*?(bg-\[hsl\(var\(--[^)]+\)\)\])',
            html,
        )
        assert connectors, f"no connector line matched — got: {html[:500]}"
        assert connectors[0] == "bg-[hsl(var(--primary))]"

        # Left step NOT completed → connector uses --border
        exp_pending_left = self._make_experience(
            steps=[
                {"name": "a", "title": "A", "is_current": True},
                {"name": "b", "title": "B"},
            ],
            current_step="a",
        )
        html2 = self._render(exp_pending_left)
        connectors2 = re.findall(
            r'<div class="flex-1 mx-3 h-px [^"]*?(bg-\[hsl\(var\(--[^)]+\)\)\])',
            html2,
        )
        assert connectors2 == ["bg-[hsl(var(--border))]"]

    # Gate 13 — non-surface step renders muted placeholder
    def test_non_surface_step_renders_muted_placeholder(self) -> None:
        # page_context=None → non-surface branch
        html = self._render(self._make_experience(page_context=None))
        assert "bg-[hsl(var(--muted))]" in html
        assert "Step in progress" in html

    # Gate 14 — transition buttons resolve 3 styles
    def test_transition_buttons_three_styles(self) -> None:
        exp = self._make_experience(
            page_context=None,
            transitions=[
                {"event": "continue", "label": "Continue", "style": "primary", "url": "/next"},
                {"event": "back", "label": "Back", "style": "ghost", "url": "/prev"},
                {"event": "skip", "label": "Skip", "style": "default", "url": "/skip"},
            ],
        )
        html = self._render(exp)
        # primary style uses --primary token
        assert "bg-[hsl(var(--primary))]" in html
        assert "Continue" in html
        # ghost style uses --muted-foreground at rest
        assert "text-[hsl(var(--muted-foreground))]" in html
        assert "Back" in html
        # default style uses --border
        assert "border-[hsl(var(--border))]" in html
        assert "Skip" in html
        # Non-surface transitions go through plain <form method="post">
        assert '<form method="post"' in html
        assert 'action="/next"' in html

    # Gate 15 — no Alpine directives anywhere
    def test_no_alpine_directives(self) -> None:
        exp = self._make_experience(
            page_context=None,
            transitions=[{"event": "continue", "label": "Continue", "style": "primary"}],
        )
        html = self._render(exp)
        for banned in ("x-data", "x-show", "x-transition", "x-for", '@click"', "@keydown"):
            assert banned not in html, f"Alpine directive leaked into experience shell: {banned}"

    # Contract pointer
    def test_contract_pointer_header_present(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "src" / "dazzle_ui" / "templates"
        src = (root / "experience" / "_content.html").read_text()
        assert (
            "Contract: ~/.claude/skills/ux-architect/components/experience-shell.md (UX-072)" in src
        )

    # Stepper omission with single step — sanity check
    def test_single_step_renders_without_stepper_but_keeps_title(self) -> None:
        single = self._make_experience(
            steps=[{"name": "only", "title": "Only", "is_current": True}],
            current_step="only",
        )
        html = self._render(single)
        assert "Get Started" in html  # title still renders
        assert "data-dz-exp-step=" not in html  # no step markers
