"""FragmentSurfaceAdapter: IR → Fragment for mode: list."""

import pytest

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.render.fragment import DataListScroll, Heading, Region, Surface, Table


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
    # Canonical (ADR-0049 Task 4e): the list body is the DataListScroll shell
    # wrapping a skeleton Table (rows hydrate from /api).
    assert isinstance(fragment.body.body, DataListScroll)
    assert isinstance(fragment.body.body.table, Table)


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
    table = fragment.body.body.table  # skeleton Table inside the DataListScroll
    assert table.columns == ("Title",)
    assert table.column_keys == ("title",)
    # rows hydrate from /api — the skeleton carries none inline
    assert table.rows == ()
    assert table.skeleton is True


def test_unsupported_mode_raises() -> None:
    """Plan 9 added CREATE+EDIT; CUSTOM remains unsupported."""
    surface = SurfaceSpec(name="x", title="X", mode=SurfaceMode.CUSTOM, entity_ref="Task")
    with pytest.raises(NotImplementedError, match="CUSTOM"):
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
    """Each field renders as Row(Heading, value). ADR-0049 Phase 2: the value
    goes through the typed cell core (`_render_cell_display`), so it's RawHTML
    (the typed rendering) rather than a plain Text."""
    from dazzle.render.fragment import Heading, RawHTML, Row

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
    assert isinstance(value, RawHTML)
    assert "Hello" in value.html


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


def test_create_mode_produces_surface_with_form_region() -> None:
    """Plan 9 — CREATE mode renders an empty form."""
    from dazzle.render.fragment import (
        Field,
        FormStack,
        Heading,
        Region,
        Submit,
        Surface,
    )

    surface = SurfaceSpec(
        name="task_create",
        title="New Task",
        mode=SurfaceMode.CREATE,
        entity_ref="Task",
    )
    ctx = {
        "fields": [
            {"name": "title", "label": "Title", "kind": "str", "required": True, "value": ""},
            {
                "name": "status",
                "label": "Status",
                "kind": "enum",
                "required": True,
                "value": "",
                "options": [("open", "Open"), ("done", "Done")],
            },
        ],
        "action": "/api/Task",
        "method": "POST",
        "submit_label": "Create",
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    assert isinstance(fragment, Surface)
    assert isinstance(fragment.header, Heading)
    assert fragment.header.body == "New Task"
    region = fragment.body
    assert isinstance(region, Region)
    assert region.kind == "form"
    form = region.body
    assert isinstance(form, FormStack)
    assert str(form.action) == "/api/Task"
    assert form.method == "POST"
    assert isinstance(form.fields[0], Field)
    assert form.fields[0].name == "title"
    assert form.fields[0].required is True
    assert isinstance(form.submit, Submit)
    assert form.submit.label == "Create"


def test_edit_mode_pre_populates_field_values() -> None:
    """Plan 9 — EDIT mode populates initial_value from row data."""
    surface = SurfaceSpec(
        name="task_edit",
        title="Edit Task",
        mode=SurfaceMode.EDIT,
        entity_ref="Task",
    )
    ctx = {
        "fields": [
            {
                "name": "title",
                "label": "Title",
                "kind": "str",
                "required": True,
                "value": "Buy milk",
            },
        ],
        "action": "/api/Task/42",
        "method": "POST",
        "submit_label": "Save",
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    form = fragment.body.body
    assert form.fields[0].initial_value == "Buy milk"
    assert form.submit.label == "Save"


def test_form_widget_kind_mapping() -> None:
    """The adapter receives WIDGET kinds (matching FieldContext.type) and
    emits Fields with the right input type. Issue #1026 surfaced that
    earlier versions assumed DSL kinds — silently swapping str↔text and
    breaking enum/bool. v0.66.45 fixed the mapping to widget-kind input.

    Mapping: DSL field type → FieldContext.type (widget) → Field.kind:

        str(N)    → text       → text
        text      → textarea   → textarea
        email     → email      → email
        int/dec   → number     → number
        bool      → checkbox   → checkbox
        date      → date       → date
        datetime  → datetime   → datetime-local
    """
    from dazzle.render.fragment import Field

    # (widget kind passed via field_dict["kind"], expected Field.kind)
    cases = [
        ("text", "text"),
        ("textarea", "textarea"),
        ("email", "email"),
        ("number", "number"),
        ("checkbox", "checkbox"),
        ("date", "date"),
        ("datetime", "datetime-local"),
    ]
    for widget_kind, expected_field_kind in cases:
        full = {
            "name": "f",
            "label": "F",
            "kind": widget_kind,
            "required": False,
            "value": "",
        }
        ctx = {
            "fields": [full],
            "action": "/x",
            "method": "POST",
            "submit_label": "Save",
        }
        surface = SurfaceSpec(name="x", mode=SurfaceMode.CREATE, entity_ref="X")
        fragment = FragmentSurfaceAdapter().build(surface, ctx)
        emitted = fragment.body.body.fields[0]
        assert isinstance(emitted, Field), (
            f"{widget_kind!r}: expected Field, got {type(emitted).__name__}"
        )
        assert emitted.kind == expected_field_kind, (
            f"{widget_kind!r}: expected kind={expected_field_kind!r}, got {emitted.kind!r}"
        )


def test_enum_field_becomes_combobox() -> None:
    """Plan 9 — enum fields render as Combobox."""
    from dazzle.render.fragment import Combobox

    ctx = {
        "fields": [
            {
                "name": "status",
                "label": "Status",
                "kind": "enum",
                "required": True,
                "value": "",
                "options": [("open", "Open"), ("done", "Done")],
            },
        ],
        "action": "/x",
        "method": "POST",
        "submit_label": "Save",
    }
    surface = SurfaceSpec(name="x", mode=SurfaceMode.CREATE, entity_ref="X")
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    emitted = fragment.body.body.fields[0]
    assert isinstance(emitted, Combobox)
    assert emitted.options == (("open", "Open"), ("done", "Done"))


def test_view_mode_appends_related_group_regions() -> None:
    """Plan 10 — related_groups produce Region(kind=related) entries
    after the detail field stack."""
    from dazzle.render.fragment import Heading, Region, Stack

    surface = SurfaceSpec(
        name="user_detail",
        title="User Detail",
        mode=SurfaceMode.VIEW,
        entity_ref="User",
    )
    ctx = {
        "fields": [{"key": "email", "label": "Email", "value": "alice@x"}],
        "region_name": "user_detail_main",
        "related_groups": [
            {"name": "tasks", "title": "Tasks", "display": "table"},
            {"name": "comments", "title": "Comments", "display": "table"},
        ],
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    # Outer Region(kind=detail) wraps a Stack: [detail-region, related-region * N]
    outer = fragment.body
    assert isinstance(outer, Region)
    assert outer.kind == "detail"
    wrapper = outer.body
    assert isinstance(wrapper, Stack)
    related_regions = [c for c in wrapper.children if isinstance(c, Region) and c.kind == "related"]
    assert len(related_regions) == 2
    titles: list[str] = []
    for r in related_regions:
        if isinstance(r.body, Stack):
            for child in r.body.children:
                if isinstance(child, Heading):
                    titles.append(child.body)
    assert "Tasks" in titles
    assert "Comments" in titles


def test_view_mode_no_related_groups_unchanged() -> None:
    """Plan 10 — VIEW without related_groups still emits Region(kind=detail) directly."""
    surface = SurfaceSpec(name="x", title="X", mode=SurfaceMode.VIEW, entity_ref="Task")
    ctx = {
        "fields": [{"key": "title", "label": "Title", "value": "Hello"}],
        "region_name": "x_main",
    }
    fragment = FragmentSurfaceAdapter().build(surface, ctx)
    assert fragment.body.kind == "detail"
    # Body is the field stack directly (not a wrapper Stack)
    from dazzle.render.fragment import Stack

    assert isinstance(fragment.body.body, Stack)
    # First child should be a Row (field), not a Region (related)
    from dazzle.render.fragment import Row

    assert isinstance(fragment.body.body.children[0], Row)
