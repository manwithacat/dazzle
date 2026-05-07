"""The Fragment type alias — discriminated union of every framework primitive.

Importers should prefer `from dazzle.render.fragment import Fragment` over
reaching into this module directly.
"""

from dazzle.render.fragment.escape import RawHTML, Slot
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
    BarChart,
    CalendarGrid,
    KanbanBoard,
    PivotTable,
    Table,
    Timeline,
)
from dazzle.render.fragment.primitives.forms import Combobox, Field, FormStack, RefPicker, Submit
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
    # Forms
    | FormStack
    | Field
    | Combobox
    | RefPicker
    | Submit
    # Escape hatches
    | RawHTML
    | Slot
)
