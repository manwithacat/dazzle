"""The Fragment type alias — discriminated union of every framework primitive.

Importers should prefer `from dazzle.render.fragment import Fragment` over
reaching into this module directly.
"""

from dazzle.render.fragment.escape import RawHTML, Script, Slot, Stylesheet
from dazzle.render.fragment.primitives.containers import (
    AppShell,
    Card,
    Drawer,
    ErrorPage,
    Modal,
    Page,
    Region,
    Surface,
    Tabs,
    Toolbar,
)
from dazzle.render.fragment.primitives.content import (
    Badge,
    EmptyState,
    Heading,
    Icon,
    Skeleton,
    Text,
)
from dazzle.render.fragment.primitives.data import (
    KPI,
    ActionCard,
    ActionGrid,
    ActivityFeed,
    AddCardRow,
    BarChart,
    BarTrack,
    BoxPlot,
    BulkActionToolbar,
    Bullet,
    CalendarGrid,
    CardPicker,
    CohortStripRegion,
    ColumnVisibilityMenu,
    ConfirmGate,
    CreateButton,
    CsvExportButton,
    DashboardCard,
    DashboardGrid,
    DataListScroll,
    DateRangePicker,
    DayTimelineRegion,
    DetailGrid,
    Diagram,
    EntityCardRegion,
    FilterBar,
    Funnel,
    GridRegion,
    Heatmap,
    Histogram,
    KanbanBoard,
    KanbanRegion,
    LazyTabPanel,
    ListFilterBar,
    ListRegion,
    MetricsGrid,
    MetricTile,
    Pagination,
    PipelineSteps,
    PivotTable,
    PivotTableRegion,
    ProfileCard,
    QueueRegion,
    Radar,
    RelatedGroup,
    SearchBox,
    Sequence,
    SortHeader,
    Sparkline,
    StageBar,
    StatusList,
    Table,
    TaskInboxRegion,
    Timeline,
    TimeSeries,
    Tree,
    WorkspaceContextSelector,
    WorkspaceDrawer,
    WorkspaceShell,
    WorkspaceToolbar,
)
from dazzle.render.fragment.primitives.forms import (
    ColorField,
    Combobox,
    DatePickerField,
    Field,
    FileUpload,
    FormSection,
    FormStack,
    MoneyField,
    RefPicker,
    RichTextField,
    SearchSelect,
    SliderField,
    Submit,
    TagsField,
    WidgetCombobox,
)
from dazzle.render.fragment.primitives.interactive import (
    Button,
    InlineEdit,
    Interactive,
    Link,
)
from dazzle.render.fragment.primitives.layout import Grid, Row, Split, Stack
from dazzle.render.fragment.primitives.navigation import (
    NavGroup,
    NavItem,
    Sidebar,
    SkipLink,
    Topbar,
)

Fragment = (
    # Layout
    Stack
    | Row
    | Split
    | Grid
    # Containers
    | Page
    | AppShell
    | Surface
    | Card
    | Region
    | Toolbar
    | Drawer
    | Modal
    | Tabs
    | ErrorPage
    # Navigation
    | Sidebar
    | Topbar
    | NavGroup
    | NavItem
    | SkipLink
    # Content
    | Text
    | Heading
    | Icon
    | Badge
    | EmptyState
    | Skeleton
    # Interactive
    | Button
    | Link
    | InlineEdit
    | Interactive
    # Data
    | Table
    | KanbanBoard
    | CalendarGrid
    | Timeline
    | KPI
    | BarChart
    | PivotTable
    | Diagram
    | TimeSeries
    | Radar
    | BoxPlot
    | Bullet
    | ActionCard
    | ProfileCard
    | MetricTile
    | MetricsGrid
    | DetailGrid
    | GridRegion
    | ListRegion
    | Histogram
    | Heatmap
    | Funnel
    | KanbanRegion
    | PivotTableRegion
    | QueueRegion
    | RelatedGroup
    | ActionGrid
    | ActivityFeed
    | StatusList
    | PipelineSteps
    | Sparkline
    | Tree
    | BarTrack
    | StageBar
    | LazyTabPanel
    | SearchBox
    | ConfirmGate
    | CardPicker
    | WorkspaceShell
    | WorkspaceToolbar
    | WorkspaceDrawer
    | WorkspaceContextSelector
    | Sequence
    | Pagination
    | CreateButton
    | BulkActionToolbar
    | CohortStripRegion
    | DayTimelineRegion
    | TaskInboxRegion
    | EntityCardRegion
    | DashboardGrid
    | DashboardCard
    | AddCardRow
    | FilterBar
    | ListFilterBar
    | DataListScroll
    | ColumnVisibilityMenu
    | SortHeader
    | CsvExportButton
    | DateRangePicker
    # Forms
    | FormStack
    | FormSection
    | Field
    | Combobox
    | RefPicker
    | SearchSelect
    | MoneyField
    | WidgetCombobox
    | TagsField
    | DatePickerField
    | ColorField
    | SliderField
    | RichTextField
    | FileUpload
    | Submit
    # Escape hatches
    | RawHTML
    | Slot
    # Assets (#1130)
    | Script
    | Stylesheet
)
