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
    Bubble,
    EmptyState,
    Heading,
    HoverCard,
    Icon,
    Message,
    MessageScroller,
    Popover,
    Skeleton,
    Text,
)
from dazzle.render.fragment.primitives.data import (
    KPI,
    ActivityFeed,
    AddCardRow,
    BarChart,
    BarTrack,
    BulkActionToolbar,
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
    GridRegion,
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
    QueueRegion,
    RelatedGroup,
    SearchBox,
    Sequence,
    SlideOver,
    SortHeader,
    StatusList,
    Table,
    Timeline,
    TimeSeries,
    WorkspaceContextSelector,
    WorkspaceDrawer,
    WorkspaceShell,
    WorkspaceToolbar,
)
from dazzle.render.fragment.primitives.forms import (
    ColorField,
    Combobox,
    Field,
    FileUpload,
    FormSection,
    FormStack,
    FormStepper,
    MoneyField,
    RefPicker,
    RichTextField,
    SearchSelect,
    SliderField,
    Submit,
    SwitchField,
    TagsField,
    Toggle,
    ToggleField,
    ToggleGroupField,
    WidgetCombobox,
)
from dazzle.render.fragment.primitives.interactive import (
    Button,
    InlineEdit,
    Interactive,
    Link,
)
from dazzle.render.fragment.primitives.layout import AspectRatio, Grid, Row, Split, Stack
from dazzle.render.fragment.primitives.navigation import (
    Breadcrumb,
    Menubar,
    NavGroup,
    NavigationMenu,
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
    | AspectRatio
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
    | Breadcrumb
    | Menubar
    | NavigationMenu
    # Content
    | Text
    | Heading
    | Icon
    | Badge
    | Bubble
    | Message
    | MessageScroller
    | HoverCard
    | Popover
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
    | MetricTile
    | MetricsGrid
    | DetailGrid
    | GridRegion
    | ListRegion
    | KanbanRegion
    | PivotTableRegion
    | QueueRegion
    | RelatedGroup
    | ActivityFeed
    | StatusList
    | PipelineSteps
    | BarTrack
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
    | EntityCardRegion
    | DashboardGrid
    | DashboardCard
    | AddCardRow
    | SlideOver
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
    | FormStepper
    | Field
    | Combobox
    | RefPicker
    | SearchSelect
    | MoneyField
    | WidgetCombobox
    | TagsField
    | ColorField
    | SliderField
    | SwitchField
    | Toggle
    | ToggleField
    | ToggleGroupField
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
