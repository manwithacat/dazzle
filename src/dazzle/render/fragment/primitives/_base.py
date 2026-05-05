"""The Fragment type alias — discriminated union of every framework primitive.

Importers should prefer `from dazzle.render.fragment import Fragment` over
reaching into this module directly.
"""

from dazzle.render.fragment.escape import RawHTML, Slot
from dazzle.render.fragment.primitives.containers import (
    Card,
    Drawer,
    Modal,
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
from dazzle.render.fragment.primitives.forms import Combobox, Field, FormStack, Submit
from dazzle.render.fragment.primitives.interactive import (
    Button,
    InlineEdit,
    Interactive,
    Link,
)
from dazzle.render.fragment.primitives.layout import Grid, Row, Split, Stack

Fragment = (
    # Layout
    Stack
    | Row
    | Split
    | Grid
    # Containers
    | Surface
    | Card
    | Region
    | Toolbar
    | Drawer
    | Modal
    | Tabs
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
    | Submit
    # Escape hatches
    | RawHTML
    | Slot
)
