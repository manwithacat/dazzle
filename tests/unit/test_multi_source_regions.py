"""Tests for multi-source workspace regions (issue #322)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import (
    AppSpec,
    DomainSpec,
    EntitySpec,
    FieldSpec,
    FieldType,
)
from dazzle.core.ir.conditions import Comparison, ComparisonOperator, ConditionExpr, ConditionValue
from dazzle.core.ir.workspaces import DisplayMode, WorkspaceRegion, WorkspaceSpec
from dazzle_ui.runtime.workspace_renderer import (
    SourceTabContext,
    build_workspace_context,
)


def _make_entity(name: str, extra_fields: list[FieldSpec] | None = None) -> EntitySpec:
    """Helper to create an entity with standard id + status fields."""
    fields = [
        FieldSpec(name="id", type=FieldType(kind="uuid"), is_primary_key=True),
        FieldSpec(
            name="status",
            type=FieldType(kind="enum", enum_values=["draft", "review", "done"]),
        ),
    ]
    if extra_fields:
        fields.extend(extra_fields)
    return EntitySpec(name=name, fields=fields)


def _make_filter(field: str, value: str) -> ConditionExpr:
    """Create a simple equality filter."""
    return ConditionExpr(
        comparison=Comparison(
            field=field,
            operator=ComparisonOperator.EQUALS,
            value=ConditionValue(literal=value),
        )
    )


def _parse(dsl: str):
    """Parse DSL and return the fragment."""
    _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
    return fragment


class TestDisplayModeEnum:
    def test_tabbed_list_exists(self) -> None:
        assert DisplayMode.TABBED_LIST == "tabbed_list"

    def test_tabbed_list_from_string(self) -> None:
        mode = DisplayMode("tabbed_list")
        assert mode == DisplayMode.TABBED_LIST


class TestWorkspaceRegionIR:
    def test_single_source_unchanged(self) -> None:
        region = WorkspaceRegion(name="tasks", source="Task")
        assert region.source == "Task"
        assert region.sources == []
        assert region.source_filters == {}

    def test_multi_source_list(self) -> None:
        region = WorkspaceRegion(
            name="review_queue",
            sources=["BookkeepingPeriod", "VATReturn", "SelfAssessmentReturn"],
        )
        assert region.source is None
        assert len(region.sources) == 3
        assert "VATReturn" in region.sources

    def test_multi_source_with_filters(self) -> None:
        filters = {
            "BookkeepingPeriod": _make_filter("status", "review"),
            "VATReturn": _make_filter("status", "prepared"),
        }
        region = WorkspaceRegion(
            name="review_queue",
            sources=["BookkeepingPeriod", "VATReturn"],
            source_filters=filters,
        )
        assert "BookkeepingPeriod" in region.source_filters
        assert "VATReturn" in region.source_filters

    def test_multi_source_display_tabbed_list(self) -> None:
        region = WorkspaceRegion(
            name="review_queue",
            sources=["A", "B"],
            display=DisplayMode.TABBED_LIST,
        )
        assert region.display == DisplayMode.TABBED_LIST


class TestParseMultiSourceRegion:
    def test_parse_source_list(self) -> None:
        """Parser should handle source: [Entity1, Entity2, Entity3] syntax."""
        dsl = """\
module test_app
app test "Test"

entity Task "Task":
  id: uuid pk
  title: str(200)

entity Bug "Bug":
  id: uuid pk
  title: str(200)

entity Feature "Feature":
  id: uuid pk
  title: str(200)

workspace dashboard "Dashboard":
  work_items:
    source: [Task, Bug, Feature]
    display: tabbed_list
"""
        fragment = _parse(dsl)
        ws = fragment.workspaces[0]
        assert len(ws.regions) == 1
        region = ws.regions[0]
        assert region.source is None
        assert region.sources == ["Task", "Bug", "Feature"]
        assert region.display == DisplayMode.TABBED_LIST

    def test_parse_source_list_default_display(self) -> None:
        """Multi-source region without explicit display should default to tabbed_list."""
        dsl = """\
module test_app
app test "Test"

entity Task "Task":
  id: uuid pk
  title: str(200)

entity Bug "Bug":
  id: uuid pk
  title: str(200)

workspace dashboard "Dashboard":
  items:
    source: [Task, Bug]
"""
        fragment = _parse(dsl)
        region = fragment.workspaces[0].regions[0]
        assert region.sources == ["Task", "Bug"]
        assert region.display == DisplayMode.TABBED_LIST

    def test_parse_filter_map(self) -> None:
        """Parser should handle filter_map: block for per-source filters."""
        dsl = """\
module test_app
app test "Test"

entity Task "Task":
  id: uuid pk
  priority: enum[open, closed]

entity Bug "Bug":
  id: uuid pk
  priority: enum[new, fixed]

workspace dashboard "Dashboard":
  review_items:
    source: [Task, Bug]
    filter_map:
      Task: priority = open
      Bug: priority = new
"""
        fragment = _parse(dsl)
        region = fragment.workspaces[0].regions[0]
        assert "Task" in region.source_filters
        assert "Bug" in region.source_filters
        task_filter = region.source_filters["Task"]
        assert task_filter.comparison is not None
        assert task_filter.comparison.field == "priority"
        assert task_filter.comparison.value.literal == "open"

    def test_single_source_still_works(self) -> None:
        """Existing single-source syntax must remain unchanged."""
        dsl = """\
module test_app
app test "Test"

entity Task "Task":
  id: uuid pk
  title: str(200)

workspace dashboard "Dashboard":
  tasks:
    source: Task
    display: list
"""
        fragment = _parse(dsl)
        region = fragment.workspaces[0].regions[0]
        assert region.source == "Task"
        assert region.sources == []
        assert region.display == DisplayMode.LIST

    def test_no_source_with_aggregates_still_works(self) -> None:
        """Aggregate-only regions must still work without source or sources."""
        dsl = """\
module test_app
app test "Test"

entity Task "Task":
  id: uuid pk
  title: str(200)

workspace dashboard "Dashboard":
  metrics:
    display: metrics
    aggregate:
      total: count(Task)
"""
        fragment = _parse(dsl)
        region = fragment.workspaces[0].regions[0]
        assert region.source is None
        assert region.sources == []
        assert "total" in region.aggregates


class TestBuildWorkspaceContext:
    def _make_appspec(self) -> AppSpec:
        return AppSpec(
            name="test_app",
            domain=DomainSpec(
                entities=[
                    _make_entity("Task"),
                    _make_entity("Bug"),
                    _make_entity("Feature"),
                ]
            ),
        )

    def test_single_source_region_unchanged(self) -> None:
        ws = WorkspaceSpec(
            name="dashboard",
            regions=[WorkspaceRegion(name="tasks", source="Task")],
        )
        ctx = build_workspace_context(ws, self._make_appspec())
        assert len(ctx.regions) == 1
        assert ctx.regions[0].source == "Task"
        assert ctx.regions[0].sources == []
        assert ctx.regions[0].source_tabs == []

    def test_multi_source_creates_tabs(self) -> None:
        ws = WorkspaceSpec(
            name="dashboard",
            regions=[
                WorkspaceRegion(
                    name="queue",
                    sources=["Task", "Bug", "Feature"],
                    display=DisplayMode.TABBED_LIST,
                )
            ],
        )
        ctx = build_workspace_context(ws, self._make_appspec())
        region = ctx.regions[0]
        assert region.sources == ["Task", "Bug", "Feature"]
        assert len(region.source_tabs) == 3

    def test_tab_labels(self) -> None:
        ws = WorkspaceSpec(
            name="dashboard",
            regions=[
                WorkspaceRegion(
                    name="queue",
                    sources=["Task", "Bug"],
                    display=DisplayMode.TABBED_LIST,
                )
            ],
        )
        ctx = build_workspace_context(ws, self._make_appspec())
        tabs = ctx.regions[0].source_tabs
        assert tabs[0].label == "Task"
        assert tabs[1].label == "Bug"

    def test_tab_labels_use_entity_display_name(self) -> None:
        """Tab labels should use entity title (display name), not internal name (#358)."""
        ws = WorkspaceSpec(
            name="dashboard",
            regions=[
                WorkspaceRegion(
                    name="businesses",
                    sources=["SoleTrader", "PartnershipMember", "CompanyContact"],
                    display=DisplayMode.TABBED_LIST,
                )
            ],
        )
        appspec = AppSpec(
            name="test_app",
            domain=DomainSpec(
                entities=[
                    EntitySpec(
                        name="SoleTrader",
                        title="Sole Trader",
                        fields=[
                            FieldSpec(name="id", type=FieldType(kind="uuid"), is_primary_key=True),
                        ],
                    ),
                    EntitySpec(
                        name="PartnershipMember",
                        title="Partnership Member",
                        fields=[
                            FieldSpec(name="id", type=FieldType(kind="uuid"), is_primary_key=True),
                        ],
                    ),
                    EntitySpec(
                        name="CompanyContact",
                        title="Company Contact",
                        fields=[
                            FieldSpec(name="id", type=FieldType(kind="uuid"), is_primary_key=True),
                        ],
                    ),
                ]
            ),
        )
        ctx = build_workspace_context(ws, appspec)
        tabs = ctx.regions[0].source_tabs
        assert tabs[0].label == "Sole Trader"
        assert tabs[1].label == "Partnership Member"
        assert tabs[2].label == "Company Contact"

    def test_tab_endpoints(self) -> None:
        ws = WorkspaceSpec(
            name="dashboard",
            regions=[
                WorkspaceRegion(
                    name="queue",
                    sources=["Task", "Bug"],
                    display=DisplayMode.TABBED_LIST,
                )
            ],
        )
        ctx = build_workspace_context(ws, self._make_appspec())
        tabs = ctx.regions[0].source_tabs
        assert tabs[0].endpoint == "/api/workspaces/dashboard/regions/queue/Task"
        assert tabs[1].endpoint == "/api/workspaces/dashboard/regions/queue/Bug"

    def test_tab_action_urls(self) -> None:
        ws = WorkspaceSpec(
            name="dashboard",
            regions=[
                WorkspaceRegion(
                    name="queue",
                    sources=["Task", "Bug"],
                    display=DisplayMode.TABBED_LIST,
                )
            ],
        )
        ctx = build_workspace_context(ws, self._make_appspec())
        tabs = ctx.regions[0].source_tabs
        assert tabs[0].action_url == "/tasks/{id}"
        assert tabs[1].action_url == "/bugs/{id}"

    def test_tabbed_list_template(self) -> None:
        ws = WorkspaceSpec(
            name="dashboard",
            regions=[
                WorkspaceRegion(
                    name="queue",
                    sources=["Task", "Bug"],
                    display=DisplayMode.TABBED_LIST,
                )
            ],
        )
        ctx = build_workspace_context(ws, self._make_appspec())
        assert ctx.regions[0].template == "workspace/regions/tabbed_list.html"

    def test_multi_source_no_single_endpoint(self) -> None:
        """Multi-source regions should not have a single endpoint."""
        ws = WorkspaceSpec(
            name="dashboard",
            regions=[
                WorkspaceRegion(
                    name="queue",
                    sources=["Task", "Bug"],
                    display=DisplayMode.TABBED_LIST,
                )
            ],
        )
        ctx = build_workspace_context(ws, self._make_appspec())
        assert ctx.regions[0].endpoint == ""


class TestPerSourceTabTemplate:
    """Verify per-source tab endpoints use tab_data.html to avoid infinite HTMX loop (#328)."""

    def test_tab_data_template_no_load_trigger(self) -> None:
        """The tab_data.html template must not contain hx-trigger='load' to prevent infinite polling."""
        template_path = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "dazzle_ui"
            / "templates"
            / "workspace"
            / "regions"
            / "tab_data.html"
        )
        content = template_path.read_text()
        assert 'hx-trigger="load"' not in content
        assert "hx-trigger='load'" not in content

    def test_tab_data_template_exists(self) -> None:
        """tab_data.html template must exist for per-source tab endpoints."""
        template_path = (
            Path(__file__).resolve().parents[2]
            / "src"
            / "dazzle_ui"
            / "templates"
            / "workspace"
            / "regions"
            / "tab_data.html"
        )
        assert template_path.exists()

    def test_per_source_region_ctx_uses_tab_data_template(self) -> None:
        """Per-source RegionContext should use tab_data.html, not tabbed_list.html."""
        ws = WorkspaceSpec(
            name="dashboard",
            regions=[
                WorkspaceRegion(
                    name="queue",
                    sources=["Task", "Bug"],
                    display=DisplayMode.TABBED_LIST,
                )
            ],
        )
        ctx = build_workspace_context(ws, self._make_appspec())
        parent_region = ctx.regions[0]
        # The parent region uses tabbed_list for the tab container
        assert parent_region.template == "workspace/regions/tabbed_list.html"
        # Create per-source copy as server.py does
        for tab in parent_region.source_tabs:
            src_region = parent_region.model_copy(
                update={
                    "template": "workspace/regions/tab_data.html",
                    "endpoint": tab.endpoint,
                    "source_tabs": [],
                }
            )
            assert src_region.template == "workspace/regions/tab_data.html"
            assert src_region.source_tabs == []
            assert src_region.endpoint == tab.endpoint

    def _make_appspec(self) -> AppSpec:
        return AppSpec(
            name="test_app",
            domain=DomainSpec(entities=[_make_entity("Task"), _make_entity("Bug")]),
        )


class TestSourceTabContext:
    def test_model_fields(self) -> None:
        tab = SourceTabContext(
            entity_name="Task",
            label="Tasks",
            endpoint="/api/workspaces/dash/regions/queue/Task",
            action_url="/tasks/{id}",
        )
        assert tab.entity_name == "Task"
        assert tab.label == "Tasks"
        assert tab.endpoint == "/api/workspaces/dash/regions/queue/Task"
        assert tab.action_url == "/tasks/{id}"

    def test_default_filter_empty(self) -> None:
        tab = SourceTabContext(entity_name="Task")
        assert tab.filter_expr == ""
