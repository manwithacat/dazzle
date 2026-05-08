"""Construct one of every primitive in the Fragment union and render each.

Adding a new primitive without adding a renderer match arm makes this test
fail with FragmentError. This is the runtime exhaustiveness check that
complements mypy's static one."""

import typing

import pytest

from dazzle.render.fragment import (
    KPI,
    URL,
    ActionCard,
    ActivityFeed,
    AppShell,
    Badge,
    BarChart,
    BarTrack,
    BoxPlot,
    Bullet,
    BulletRow,
    Button,
    CalendarGrid,
    Card,
    Combobox,
    ConfirmGate,
    CsvExportButton,
    DateRangePicker,
    DetailGrid,
    Diagram,
    Drawer,
    EmptyState,
    ErrorPage,
    Field,
    FilterBar,
    FilterColumn,
    FormStack,
    Fragment,
    Grid,
    Heading,
    Icon,
    InlineEdit,
    Interactive,
    KanbanBoard,
    LazyTab,
    LazyTabPanel,
    Link,
    MetricsGrid,
    MetricTile,
    Modal,
    NavGroup,
    NavItem,
    Page,
    PipelineStage,
    PipelineSteps,
    PivotTable,
    ProfileCard,
    Radar,
    RawHTML,
    RefPicker,
    Region,
    Row,
    SearchBox,
    Sidebar,
    Skeleton,
    SkipLink,
    Slot,
    SortHeader,
    Sparkline,
    Split,
    Stack,
    StageBar,
    StatusList,
    StatusListEntry,
    Submit,
    Surface,
    Table,
    Tabs,
    TargetSelector,
    Text,
    Timeline,
    TimeSeries,
    Toolbar,
    Topbar,
    Tree,
    TreeNode,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def _sample_for(primitive_type: type) -> object:
    """Return a constructed instance of `primitive_type` with safe defaults.

    Adding a new primitive means adding a sample here. The if-chain is
    intentional — keeps construction co-located with the type and visible
    in diffs."""
    if primitive_type is Stack:
        return Stack(children=(Text("a"),))
    if primitive_type is Row:
        return Row(children=(Text("a"),))
    if primitive_type is Split:
        return Split(start=Text("L"), end=Text("R"))
    if primitive_type is Grid:
        return Grid(children=(Text("a"),))
    if primitive_type is Surface:
        return Surface(body=Text("body"))
    if primitive_type is Page:
        return Page(title="X", body=Text("x"))
    if primitive_type is AppShell:
        return AppShell(body=Text("body"))
    if primitive_type is NavItem:
        return NavItem(label="Home", href=URL("/"))
    if primitive_type is NavGroup:
        return NavGroup(label="Group", items=(NavItem(label="A", href=URL("/a")),))
    if primitive_type is Sidebar:
        return Sidebar()
    if primitive_type is Topbar:
        return Topbar(title="App")
    if primitive_type is SkipLink:
        return SkipLink()
    if primitive_type is Card:
        return Card(body=Text("body"))
    if primitive_type is Region:
        return Region(kind="list", body=Text("body"))
    if primitive_type is Toolbar:
        return Toolbar(label="actions")
    if primitive_type is Drawer:
        return Drawer(body=Text("body"))
    if primitive_type is Modal:
        return Modal(body=Text("body"))
    if primitive_type is Tabs:
        return Tabs(tabs=(("a", Text("A")),))
    if primitive_type is ErrorPage:
        return ErrorPage(code=404, message="Not Found")
    if primitive_type is Text:
        return Text("hello")
    if primitive_type is Heading:
        return Heading("title")
    if primitive_type is Icon:
        return Icon(name="check")
    if primitive_type is Badge:
        return Badge(label="new")
    if primitive_type is EmptyState:
        return EmptyState(title="t", description="d")
    if primitive_type is Skeleton:
        return Skeleton()
    if primitive_type is Button:
        return Button(label="ok")
    if primitive_type is Link:
        return Link(label="open", href=URL("/x"))
    if primitive_type is InlineEdit:
        return InlineEdit(field_name="title", value="v")
    if primitive_type is Interactive:
        return Interactive(
            child=Text("c"),
            hx_get=URL("/x"),
            hx_target=TargetSelector("#t"),
        )
    if primitive_type is Table:
        return Table(columns=("a",), rows=(("v",),))
    if primitive_type is KanbanBoard:
        return KanbanBoard(columns=(("col", ()),))
    if primitive_type is CalendarGrid:
        return CalendarGrid()
    if primitive_type is Timeline:
        return Timeline(events=(("e", "2026-01-01"),))
    if primitive_type is KPI:
        return KPI(label="rev", value="1")
    if primitive_type is BarChart:
        return BarChart(label="x", buckets=(("a", 1),))
    if primitive_type is PivotTable:
        return PivotTable(
            label="x",
            rows=("r",),
            columns=("c",),
            cells={("r", "c"): 0},
        )
    if primitive_type is Diagram:
        return Diagram(nodes=("A", "B"), edges=(("A", "B"),))
    if primitive_type is TimeSeries:
        return TimeSeries(label="x", points=(("a", 1.0),))
    if primitive_type is Radar:
        return Radar(label="x", axes=(("a", 1.0), ("b", 2.0), ("c", 3.0)))
    if primitive_type is BoxPlot:
        return BoxPlot(label="x", groups=(("g", 0.0, 1.0, 2.0, 3.0, 4.0),))
    if primitive_type is Bullet:
        return Bullet(rows=(BulletRow(label="X", actual=50.0),), max_value=100.0)
    if primitive_type is BulletRow:
        return BulletRow(label="X", actual=50.0)
    if primitive_type is Sparkline:
        return Sparkline(points=(("a", 1.0), ("b", 2.0)))
    if primitive_type is PipelineSteps:
        return PipelineSteps(stages=(PipelineStage(label="Step"),))
    if primitive_type is PipelineStage:
        return PipelineStage(label="Step")
    if primitive_type is Tree:
        return Tree(nodes=(TreeNode(label="root"),))
    if primitive_type is TreeNode:
        return TreeNode(label="node")
    if primitive_type is ActionCard:
        return ActionCard(label="X")
    if primitive_type is ProfileCard:
        return ProfileCard(primary="Alice")
    if primitive_type is MetricTile:
        return MetricTile(label="X", value="0")
    if primitive_type is MetricsGrid:
        return MetricsGrid(tiles=(MetricTile(label="X", value="0"),))
    if primitive_type is DetailGrid:
        return DetailGrid(rows=(("Label", Text("value")),))
    if primitive_type is ActivityFeed:
        return ActivityFeed(items=(("now", "Alice", "did the thing"),))
    if primitive_type is StatusList:
        return StatusList(entries=(StatusListEntry(title="OK", state="positive"),))
    if primitive_type is StatusListEntry:
        return StatusListEntry(title="OK")
    if primitive_type is BarTrack:
        return BarTrack(rows=(("X", 1.0, "1", 50.0),), max_value=100.0)
    if primitive_type is StageBar:
        return StageBar(stages=(("X", 1, False),))
    if primitive_type is LazyTabPanel:
        return LazyTabPanel(
            region_name="t",
            tabs=(LazyTab(key="a", label="A", endpoint=URL("/a")),),
        )
    if primitive_type is SearchBox:
        return SearchBox(name="x", fts_endpoint=URL("/api/fts/X"))
    if primitive_type is ConfirmGate:
        return ConfirmGate(state="off")
    if primitive_type is FilterBar:
        return FilterBar(
            endpoint=URL("/x"),
            region_name="r",
            columns=(FilterColumn(key="k", label="L", options=()),),
        )
    if primitive_type is SortHeader:
        return SortHeader(label="L", column_key="k", endpoint=URL("/x"), region_name="r")
    if primitive_type is CsvExportButton:
        return CsvExportButton(endpoint=URL("/x"))
    if primitive_type is DateRangePicker:
        return DateRangePicker(endpoint=URL("/x"), region_name="r")
    if primitive_type is FormStack:
        return FormStack(action=URL("/x"), fields=(Field(name="t", label="T"),))
    if primitive_type is Field:
        return Field(name="t", label="T")
    if primitive_type is Combobox:
        return Combobox(name="s", label="S", options=(("a", "A"),))
    if primitive_type is RefPicker:
        return RefPicker(name="r", label="R", ref_api=URL("/x"))
    if primitive_type is Submit:
        return Submit(label="Save")
    if primitive_type is RawHTML:
        return RawHTML("<span>raw</span>")
    if primitive_type is Slot:
        # Slot is special-cased below — it raises at render time.
        return Slot(name="s")
    raise AssertionError(f"no sample defined for {primitive_type!r}")


def test_every_primitive_in_fragment_alias_is_renderable() -> None:
    r = FragmentRenderer()
    for ptype in typing.get_args(Fragment):
        sample = _sample_for(ptype)
        if isinstance(sample, Slot):
            # Slot deliberately raises at render time (Task 17). Verify that.
            with pytest.raises(Exception, match="unfilled slot"):
                r.render(sample)  # type: ignore[arg-type]
            continue
        out = r.render(sample)  # type: ignore[arg-type]
        assert isinstance(out, str)
        assert out, f"{ptype.__name__} rendered to empty string"
