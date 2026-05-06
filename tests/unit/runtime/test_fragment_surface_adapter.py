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
    surface = SurfaceSpec(name="x", title="X", mode=SurfaceMode.VIEW, entity_ref="Task")
    with pytest.raises(NotImplementedError, match="VIEW"):
        FragmentSurfaceAdapter().build(surface, {})


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
