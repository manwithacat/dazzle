"""Framework primitive types."""

from dazzle.render.fragment.primitives._base import Fragment
from dazzle.render.fragment.primitives.containers import (
    AppShell,
    Card,
    Drawer,
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
from dazzle.render.fragment.primitives.navigation import NavGroup, NavItem, Sidebar, Topbar

__all__ = [
    "Fragment",
    # layout
    "Stack",
    "Row",
    "Split",
    "Grid",
    # containers
    "Page",
    "AppShell",
    "Surface",
    "Card",
    "Region",
    "Toolbar",
    "Drawer",
    "Modal",
    "Tabs",
    # content
    "Text",
    "Heading",
    "Icon",
    "Badge",
    "EmptyState",
    "Skeleton",
    # interactive
    "Button",
    "Link",
    "InlineEdit",
    "Interactive",
    # data
    "Table",
    "KanbanBoard",
    "CalendarGrid",
    "Timeline",
    "KPI",
    "BarChart",
    "PivotTable",
    # forms
    "FormStack",
    "Field",
    "Combobox",
    "RefPicker",
    "Submit",
    # navigation
    "Sidebar",
    "Topbar",
    "NavGroup",
    "NavItem",
]
