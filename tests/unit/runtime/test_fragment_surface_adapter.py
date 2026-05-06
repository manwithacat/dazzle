"""FragmentSurfaceAdapter: IR → Fragment for mode: list."""

import pytest

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.render.fragment import Heading, Region, Surface, Table
from dazzle_back.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter


def test_list_mode_produces_surface_with_heading_and_region() -> None:
    surface = SurfaceSpec(
        name="task_list",
        title="Task List",
        mode=SurfaceMode.LIST,
        entity_ref="Task",
    )
    ctx = {
        "items": [{"id": "1", "title": "Buy milk"}, {"id": "2", "title": "Walk dog"}],
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "region_name": "task_list_main",
        "endpoint": "/api/test",
        "total": 2,
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    assert isinstance(fragment, Surface)
    assert isinstance(fragment.header, Heading)
    assert fragment.header.body == "Task List"
    assert isinstance(fragment.body, Region)
    assert fragment.body.kind == "list"
    assert isinstance(fragment.body.body, Table)


def test_list_mode_table_columns_match_ctx() -> None:
    surface = SurfaceSpec(name="x", title="X", mode=SurfaceMode.LIST, entity_ref="Task")
    ctx = {
        "items": [{"id": "1", "title": "Hello"}],
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "region_name": "x_main",
        "endpoint": "/api/x",
        "total": 1,
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    table = fragment.body.body
    assert table.columns == ("Title",)
    assert table.rows == (("Hello",),)


def test_unsupported_mode_raises() -> None:
    """Plan 8 added VIEW; CREATE remains unsupported (Plan 9 closure)."""
    surface = SurfaceSpec(name="x", title="X", mode=SurfaceMode.CREATE, entity_ref="Task")
    with pytest.raises(NotImplementedError, match="CREATE"):
        FragmentSurfaceAdapter().build(surface, {})


def test_view_mode_produces_surface_with_detail_region() -> None:
    """Plan 8 — SurfaceMode.VIEW renders fields as definition-list Region."""
    from dazzle.render.fragment import Heading, Region, Stack, Surface

    surface = SurfaceSpec(
        name="task_detail",
        title="Task Detail",
        mode=SurfaceMode.VIEW,
        entity_ref="Task",
    )
    ctx = {
        "fields": [
            {"key": "title", "label": "Title", "value": "Buy milk"},
            {"key": "status", "label": "Status", "value": "open"},
        ],
        "region_name": "task_detail_main",
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    assert isinstance(fragment, Surface)
    assert isinstance(fragment.header, Heading)
    assert fragment.header.body == "Task Detail"
    assert isinstance(fragment.body, Region)
    assert fragment.body.kind == "detail"
    assert isinstance(fragment.body.body, Stack)
    assert len(fragment.body.body.children) == 2


def test_view_mode_field_row_shape() -> None:
    """Plan 8 — each field renders as Row(Heading, Text)."""
    from dazzle.render.fragment import Heading, Row, Text

    surface = SurfaceSpec(name="x", title="X", mode=SurfaceMode.VIEW, entity_ref="Task")
    ctx = {
        "fields": [{"key": "title", "label": "Title", "value": "Hello"}],
        "region_name": "x_main",
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    stack = fragment.body.body
    first_row = stack.children[0]
    assert isinstance(first_row, Row)
    label, value = first_row.children
    assert isinstance(label, Heading)
    assert label.body == "Title"
    assert isinstance(value, Text)
    assert value.body == "Hello"


def test_view_mode_handles_no_fields_gracefully() -> None:
    """Plan 8 — empty fields renders EmptyState (Stack invariant requires >=1 child)."""
    from dazzle.render.fragment import EmptyState

    surface = SurfaceSpec(name="x", title="X", mode=SurfaceMode.VIEW, entity_ref="Task")
    ctx = {"fields": [], "region_name": "x_main"}
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    assert isinstance(fragment.body.body, EmptyState)


def test_empty_items_still_produces_well_formed_fragment() -> None:
    """Zero rows is a valid empty list — should produce an EmptyState
    or an empty table without raising."""
    surface = SurfaceSpec(name="x", title="X", mode=SurfaceMode.LIST, entity_ref="Task")
    ctx = {
        "items": [],
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "region_name": "x_main",
        "endpoint": "/api/x",
        "total": 0,
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    assert isinstance(fragment, Surface)
