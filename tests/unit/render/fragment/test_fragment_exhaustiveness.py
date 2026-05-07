"""Construct one of every primitive in the Fragment union and render each.

Adding a new primitive without adding a renderer match arm makes this test
fail with FragmentError. This is the runtime exhaustiveness check that
complements mypy's static one."""

import typing

import pytest

from dazzle.render.fragment import (
    KPI,
    URL,
    AppShell,
    Badge,
    BarChart,
    Button,
    CalendarGrid,
    Card,
    Combobox,
    Drawer,
    EmptyState,
    Field,
    FormStack,
    Fragment,
    Grid,
    Heading,
    Icon,
    InlineEdit,
    Interactive,
    KanbanBoard,
    Link,
    Modal,
    NavGroup,
    NavItem,
    Page,
    PivotTable,
    RawHTML,
    RefPicker,
    Region,
    Row,
    Sidebar,
    Skeleton,
    Slot,
    Split,
    Stack,
    Submit,
    Surface,
    Table,
    Tabs,
    TargetSelector,
    Text,
    Timeline,
    Toolbar,
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
