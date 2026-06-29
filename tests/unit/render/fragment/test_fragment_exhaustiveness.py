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
    ActionGrid,
    ActivityFeed,
    AddCardRow,
    AppShell,
    Badge,
    BarChart,
    BarTrack,
    BoxPlot,
    BulkActionToolbar,
    Bullet,
    BulletRow,
    Button,
    CalendarGrid,
    Card,
    CardPicker,
    CardPickerEntry,
    CohortStripCell,
    CohortStripLensTab,
    CohortStripRegion,
    ColorField,
    ColumnVisibilityMenu,
    Combobox,
    ConfirmGate,
    CreateButton,
    CsvExportButton,
    DashboardCard,
    DashboardGrid,
    DashboardNotice,
    DataListScroll,
    DatePickerField,
    DateRangePicker,
    DayTimelineRegion,
    DayTimelineSlot,
    DetailGrid,
    Diagram,
    Drawer,
    EmptyState,
    EntityCardRegion,
    EntityCardSection,
    ErrorPage,
    Field,
    FileUpload,
    FilterBar,
    FilterColumn,
    FormSection,
    FormStack,
    FormStepper,
    Fragment,
    Funnel,
    FunnelStage,
    Grid,
    GridCell,
    GridRegion,
    Heading,
    Heatmap,
    HeatmapRow,
    Histogram,
    HistogramBin,
    Icon,
    InlineEdit,
    Interactive,
    KanbanBoard,
    KanbanCard,
    KanbanColumn,
    KanbanRegion,
    LazyTab,
    LazyTabPanel,
    Link,
    ListColumn,
    ListFilterBar,
    ListRegion,
    MetricsGrid,
    MetricTile,
    Modal,
    MoneyField,
    NavGroup,
    NavItem,
    Page,
    Pagination,
    PipelineStage,
    PipelineSteps,
    PivotDimSpec,
    PivotTable,
    PivotTableRegion,
    ProfileCard,
    QueueBadgeColumn,
    QueueDateColumn,
    QueueMetric,
    QueueRegion,
    QueueRow,
    QueueTransition,
    Radar,
    RawHTML,
    RefPicker,
    Region,
    RelatedGroup,
    RelatedTab,
    RichTextField,
    Row,
    Script,
    SearchBox,
    SearchSelect,
    Sequence,
    Sidebar,
    Skeleton,
    SkipLink,
    SliderField,
    Slot,
    SortHeader,
    Sparkline,
    Split,
    Stack,
    StageBar,
    StatusList,
    StatusListEntry,
    Stylesheet,
    Submit,
    Surface,
    Table,
    Tabs,
    TagsField,
    TargetSelector,
    TaskInboxItem,
    TaskInboxRegion,
    TaskInboxSummaryChip,
    Text,
    Timeline,
    TimelineEvent,
    TimeSeries,
    Toolbar,
    Topbar,
    Tree,
    TreeNode,
    WidgetCombobox,
    WorkspaceContextSelector,
    WorkspaceDrawer,
    WorkspacePrimaryAction,
    WorkspaceShell,
    WorkspaceToolbar,
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
    if primitive_type is DataListScroll:
        return DataListScroll(
            table=Table(columns=("a",), rows=(), skeleton=True, hx_endpoint="/api/x"),
            table_id="x",
            empty_title="No items",
        )
    if primitive_type is ColumnVisibilityMenu:
        return ColumnVisibilityMenu(columns=(("a", "A"),))
    if primitive_type is RelatedGroup:
        return RelatedGroup(
            group_id="g",
            label="Tasks",
            display="table",
            tabs=(RelatedTab(tab_id="t", label="Tasks", headers=("Title",), rows=(("x",),)),),
        )
    if primitive_type is ListFilterBar:
        return ListFilterBar(
            tbody_id="x-body",
            endpoint=URL("/api/x"),
            columns=(FilterColumn(key="status", label="Status", options=(("o", "Open"),)),),
        )
    if primitive_type is KanbanBoard:
        return KanbanBoard(columns=(("col", ()),))
    if primitive_type is CalendarGrid:
        return CalendarGrid()
    if primitive_type is Timeline:
        return Timeline(events=(TimelineEvent(title="e", date_label="just now"),))
    if primitive_type is TimelineEvent:
        return TimelineEvent(title="e", date_label="just now")
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
        # v0.66.118: Diagram now accepts mermaid_source as an alternative
        # to nodes; node/edge form remains valid and is what we exercise here.
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
    if primitive_type is ActionGrid:
        return ActionGrid(cards=(ActionCard(label="X"),))
    if primitive_type is ProfileCard:
        return ProfileCard(primary="Alice")
    if primitive_type is MetricTile:
        return MetricTile(label="X", value="0")
    if primitive_type is MetricsGrid:
        return MetricsGrid(tiles=(MetricTile(label="X", value="0"),))
    if primitive_type is DetailGrid:
        return DetailGrid(rows=(("Label", Text("value")),))
    if primitive_type is GridRegion:
        return GridRegion(cells=(GridCell(title="A"),))
    if primitive_type is GridCell:
        return GridCell(title="A")
    if primitive_type is ListRegion:
        return ListRegion(
            columns=(ListColumn(key="k", label="K"),),
            rows=(("v",),),
        )
    if primitive_type is ListColumn:
        return ListColumn(key="k", label="K")
    if primitive_type is Histogram:
        return Histogram(
            label="x",
            bins=(HistogramBin(label="0-10", count=4, low=0.0, high=10.0),),
        )
    if primitive_type is HistogramBin:
        return HistogramBin(label="0-10", count=4, low=0.0, high=10.0)
    if primitive_type is Heatmap:
        return Heatmap(
            columns=("X",),
            rows=(HeatmapRow(label="A", cells=(1.0,)),),
        )
    if primitive_type is HeatmapRow:
        return HeatmapRow(label="A", cells=(1.0,))
    if primitive_type is PivotTableRegion:
        return PivotTableRegion(
            dim_specs=(PivotDimSpec(name="x", label="X"),),
            measure_keys=("count",),
            rows=({"x": "a", "count": 1},),
        )
    if primitive_type is PivotDimSpec:
        return PivotDimSpec(name="x", label="X")
    if primitive_type is QueueRegion:
        return QueueRegion(rows=(QueueRow(row_id="1", title="A"),))
    if primitive_type is QueueRow:
        return QueueRow(row_id="1", title="A")
    if primitive_type is QueueMetric:
        return QueueMetric(label="L", value="1")
    if primitive_type is QueueTransition:
        return QueueTransition(label="Approve", to_state="approved")
    if primitive_type is QueueBadgeColumn:
        return QueueBadgeColumn(key="severity", value="high")
    if primitive_type is QueueDateColumn:
        return QueueDateColumn(label="Due", timeago_str="just now")
    if primitive_type is Funnel:
        return Funnel(stages=(FunnelStage(label="lead", count=10),))
    if primitive_type is FunnelStage:
        return FunnelStage(label="lead", count=10)
    if primitive_type is KanbanRegion:
        return KanbanRegion(columns=(KanbanColumn(label="todo", cards=()),))
    if primitive_type is KanbanColumn:
        return KanbanColumn(label="todo", cards=())
    if primitive_type is KanbanCard:
        return KanbanCard(title="Task")
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
        return SearchBox(name="x", fts_endpoint=URL("/_dazzle/fts/X"))
    if primitive_type is WorkspaceShell:
        return WorkspaceShell(workspace_name="ws", title="W", body=Text("body"))
    if primitive_type is WorkspacePrimaryAction:
        return WorkspacePrimaryAction(label="L", route="/x")
    if primitive_type is WorkspaceToolbar:
        return WorkspaceToolbar()
    if primitive_type is WorkspaceDrawer:
        return WorkspaceDrawer()
    if primitive_type is Sequence:
        return Sequence(children=(Text("a"), Text("b")))
    if primitive_type is Pagination:
        return Pagination(
            region_name="t",
            endpoint=URL("/api/x"),
            total=100,
            page=3,
            page_size=10,
        )
    if primitive_type is CreateButton:
        return CreateButton(href=URL("/x"), entity_name="Item")
    if primitive_type is BulkActionToolbar:
        return BulkActionToolbar()
    if primitive_type is CohortStripRegion:
        return CohortStripRegion(
            region_name="cohort",
            endpoint=URL("/api/cohort"),
            lenses=(CohortStripLensTab(id="x", label="X", is_active=True),),
            cells=(),
        )
    if primitive_type is CohortStripLensTab:
        return CohortStripLensTab(id="x", label="X", is_active=True)
    if primitive_type is CohortStripCell:
        return CohortStripCell(member_id="p1", member_name="A", primary_value="0")
    if primitive_type is DayTimelineRegion:
        return DayTimelineRegion(region_name="day", slots=())
    if primitive_type is DayTimelineSlot:
        return DayTimelineSlot(slot_id="s1", label="P1")
    if primitive_type is TaskInboxRegion:
        return TaskInboxRegion(region_name="inbox", items=())
    if primitive_type is TaskInboxItem:
        return TaskInboxItem(item_id="i1", icon="register", title="x")
    if primitive_type is TaskInboxSummaryChip:
        return TaskInboxSummaryChip(chip_id="c1", count=0, label="x")
    if primitive_type is EntityCardRegion:
        return EntityCardRegion(region_name="card", sections=())
    if primitive_type is EntityCardSection:
        return EntityCardSection(section_id="s", label="L")
    if primitive_type is WorkspaceContextSelector:
        return WorkspaceContextSelector(workspace_name="d", options_url="/x", label="L")
    if primitive_type is DashboardGrid:
        return DashboardGrid(cards=())
    if primitive_type is DashboardCard:
        return DashboardCard(
            card_id="card-0",
            name="r",
            title="R",
            display="LIST",
            col_span=6,
            row_order=0,
            hx_endpoint="/x",
        )
    if primitive_type is DashboardNotice:
        return DashboardNotice(title="N")
    if primitive_type is AddCardRow:
        return AddCardRow(picker=CardPicker(entries=(), catalog_json="[]"))
    if primitive_type is CardPicker:
        return CardPicker(
            entries=(CardPickerEntry(name="t", title="Tasks", entity="Task", display="list"),),
            catalog_json="[]",
        )
    if primitive_type is CardPickerEntry:
        return CardPickerEntry(name="t", title="Tasks", entity="Task", display="list")
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
    if primitive_type is FormSection:
        return FormSection(title="S", fields=(Field(name="t", label="T"),))
    if primitive_type is FormStack:
        return FormStack(action=URL("/x"), fields=(Field(name="t", label="T"),))
    if primitive_type is Field:
        return Field(name="t", label="T")
    if primitive_type is Combobox:
        return Combobox(name="s", label="S", options=(("a", "A"),))
    if primitive_type is RefPicker:
        return RefPicker(name="r", label="R", ref_api=URL("/x"))
    if primitive_type is SearchSelect:
        return SearchSelect(name="ss", label="SS", endpoint=URL("/search"))
    if primitive_type is FormStepper:
        return FormStepper(sections=("One", "Two"))
    if primitive_type is MoneyField:
        return MoneyField(name="amt", label="Amount")
    if primitive_type is WidgetCombobox:
        return WidgetCombobox(name="wc", label="WC", options=(("a", "A"),))
    if primitive_type is TagsField:
        return TagsField(name="tg", label="Tags")
    if primitive_type is DatePickerField:
        return DatePickerField(name="dp", label="Date")
    if primitive_type is ColorField:
        return ColorField(name="cl", label="Colour")
    if primitive_type is SliderField:
        return SliderField(name="sl", label="Slider")
    if primitive_type is RichTextField:
        return RichTextField(name="rt", label="Rich")
    if primitive_type is FileUpload:
        return FileUpload(name="f", label="F", upload_url=URL("/uploads"))
    if primitive_type is Submit:
        return Submit(label="Save")
    if primitive_type is RawHTML:
        return RawHTML("<span>raw</span>")
    if primitive_type is Slot:
        # Slot is special-cased below — it raises at render time.
        return Slot(name="s")
    if primitive_type is Script:
        return Script(body="console.log('test');")
    if primitive_type is Stylesheet:
        return Stylesheet(body="body { color: red; }")
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
