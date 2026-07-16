"""#1593 bulk chrome gate + #1592 row drill-in stopPropagation policy."""

from __future__ import annotations

from dazzle.core import ir
from dazzle.core.ir import FieldModifier, FieldTypeKind, SurfaceMode
from dazzle.page.converters.template_compiler import compile_surface_to_context
from dazzle.render.fragment.renderer._data_row import _render_table_row


def _task_entity() -> ir.EntitySpec:
    return ir.EntitySpec(
        name="Task",
        title="Task",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="title",
                type=ir.FieldType(kind=FieldTypeKind.STR, max_length=200),
                modifiers=[FieldModifier.REQUIRED],
            ),
        ],
    )


def _list_surface(*, bulk: bool) -> ir.SurfaceSpec:
    elements = [ir.SurfaceElement(field_name="title", label="Title")]
    ux = ir.UXSpec(
        bulk_actions=(
            [
                ir.BulkActionSpec(
                    name="delete",
                    label="Delete selected",
                    field="status",
                    target_value="deleted",
                )
            ]
            if bulk
            else []
        ),
    )
    return ir.SurfaceSpec(
        name="task_list",
        title="Tasks",
        entity_ref="Task",
        mode=SurfaceMode.LIST,
        sections=[ir.SurfaceSection(name="main", title="Main", elements=elements)],
        actions=[],
        ux=ux,
    )


def test_compiler_bulk_actions_off_without_ux_block() -> None:
    """#1593: list shell must not force bulk chrome without DSL opt-in."""
    ctx = compile_surface_to_context(_list_surface(bulk=False), _task_entity())
    assert ctx.table is not None
    assert ctx.table.bulk_actions is False


def test_compiler_bulk_actions_on_when_ux_declares() -> None:
    ctx = compile_surface_to_context(_list_surface(bulk=True), _task_entity())
    assert ctx.table is not None
    assert ctx.table.bulk_actions is True


def test_row_plain_cell_does_not_stop_propagation() -> None:
    """#1592: display-only cell allows row hx-get click to fire."""
    html = _render_table_row(
        {
            "entity_name": "Task",
            "api_endpoint": "/api/tasks",
            "detail_url_template": "/app/task/{id}",
            "columns": [{"key": "title", "type": "str"}],
            "bulk_actions": False,
            "inline_editable": [],
        },
        {"id": "abc", "title": "Fix the printer"},
    )
    assert 'hx-trigger="click"' in html
    # Data cell open tag must not stopPropagation
    assert 'class="dz-tr-cell" onclick="event.stopPropagation()"' not in html
    # Actions cell still isolates
    assert "dz-tr-actions-cell" in html
    assert "stopPropagation" in html  # actions only


def test_row_inline_edit_cell_does_not_stop_propagation() -> None:
    """#1598: C2.3-editable display cells still bubble single-click for drill.

    Grid edit is dblclick-only; stopPropagation on every inline_editable td
    made row hx-get dead once C2.3 marked most columns editable.
    """
    html = _render_table_row(
        {
            "entity_name": "Task",
            "api_endpoint": "/api/tasks",
            "detail_url_template": "/app/task/{id}",
            "columns": [{"key": "title", "type": "text"}],
            "bulk_actions": False,
            "inline_editable": ["title"],
        },
        {"id": "abc", "title": "Fix the printer"},
    )
    assert "dz-tr-cell-display" in html
    assert 'data-dz-grid-edit="title"' in html
    assert 'class="dz-tr-cell" onclick="event.stopPropagation()"' not in html
    # Actions still isolate
    assert "dz-tr-actions-cell" in html
    assert "stopPropagation" in html


def test_row_without_bulk_has_no_row_checkbox() -> None:
    html = _render_table_row(
        {
            "entity_name": "Task",
            "api_endpoint": "/api/tasks",
            "columns": [{"key": "title", "type": "str"}],
            "bulk_actions": False,
        },
        {"id": "1", "title": "T"},
    )
    assert "dz-tr-checkbox" not in html
    assert "data-dz-grid-select" not in html
