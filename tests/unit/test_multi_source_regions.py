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
