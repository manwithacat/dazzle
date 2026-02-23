"""Tests for DataTable UXSpec → template context wiring."""

from __future__ import annotations

from dazzle.core import ir
from dazzle.core.ir import FieldModifier, FieldTypeKind, SurfaceMode
from dazzle_ui.converters.template_compiler import compile_surface_to_context

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _task_entity(
    *,
    with_enum: bool = False,
    with_bool: bool = False,
    with_state_machine: bool = False,
) -> ir.EntitySpec:
    """Build a minimal Task entity for testing."""
    fields: list[ir.FieldSpec] = [
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
    ]
    if with_enum:
        fields.append(
            ir.FieldSpec(
                name="priority",
                type=ir.FieldType(
                    kind=FieldTypeKind.ENUM,
                    enum_values=["low", "medium", "high"],
                ),
            )
        )
    if with_bool:
        fields.append(
            ir.FieldSpec(
                name="completed",
                type=ir.FieldType(kind=FieldTypeKind.BOOL),
            )
        )

    sm = None
    if with_state_machine:
        fields.append(
            ir.FieldSpec(
                name="status",
                type=ir.FieldType(
                    kind=FieldTypeKind.ENUM,
                    enum_values=["open", "in_progress", "done"],
                ),
            )
        )
        sm = ir.StateMachineSpec(
            status_field="status",
            states=["open", "in_progress", "done"],
            transitions=[
                ir.StateTransition(from_state="open", to_state="in_progress"),
                ir.StateTransition(from_state="in_progress", to_state="done"),
            ],
        )

    return ir.EntitySpec(
        name="Task",
        title="Task",
        fields=fields,
        state_machine=sm,
    )


def _list_surface(
    *,
    ux: ir.UXSpec | None = None,
    field_names: list[str] | None = None,
) -> ir.SurfaceSpec:
    """Build a minimal LIST surface."""
    names = field_names or ["title"]
    elements = [
        ir.SurfaceElement(field_name=fn, label=fn.replace("_", " ").title()) for fn in names
    ]
    return ir.SurfaceSpec(
        name="task_list",
        title="Tasks",
        entity_ref="Task",
        mode=SurfaceMode.LIST,
        sections=[ir.SurfaceSection(name="main", title="Main", elements=elements)],
        actions=[],
        ux=ux,
    )


# ---------------------------------------------------------------------------
# Tests — column attributes from UX sort
# ---------------------------------------------------------------------------


class TestColumnSortable:
    """Columns should be marked sortable when ux.sort is declared."""

    def test_columns_get_sortable_from_ux_sort(self) -> None:
        ux = ir.UXSpec(sort=[ir.SortSpec(field="title", direction="asc")])
        surface = _list_surface(ux=ux)
        entity = _task_entity()

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        for col in ctx.table.columns:
            assert col.sortable is True

    def test_columns_not_sortable_without_ux_sort(self) -> None:
        surface = _list_surface()
        entity = _task_entity()

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        for col in ctx.table.columns:
            assert col.sortable is False


# ---------------------------------------------------------------------------
# Tests — column filter attributes from UX filter
# ---------------------------------------------------------------------------


class TestColumnFilterable:
    """Columns should be marked filterable when ux.filter references them."""

    def test_columns_get_filterable_from_ux_filter(self) -> None:
        ux = ir.UXSpec(filter=["priority"])
        surface = _list_surface(ux=ux, field_names=["title", "priority"])
        entity = _task_entity(with_enum=True)

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        cols_by_key = {c.key: c for c in ctx.table.columns}
        assert cols_by_key["priority"].filterable is True
        assert cols_by_key["title"].filterable is False

    def test_enum_filter_type_select(self) -> None:
        ux = ir.UXSpec(filter=["priority"])
        surface = _list_surface(ux=ux, field_names=["title", "priority"])
        entity = _task_entity(with_enum=True)

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        priority_col = next(c for c in ctx.table.columns if c.key == "priority")
        assert priority_col.filter_type == "select"
        assert len(priority_col.filter_options) == 3
        assert priority_col.filter_options[0]["value"] == "low"

    def test_bool_filter_type_select(self) -> None:
        ux = ir.UXSpec(filter=["completed"])
        surface = _list_surface(ux=ux, field_names=["title", "completed"])
        entity = _task_entity(with_bool=True)

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        completed_col = next(c for c in ctx.table.columns if c.key == "completed")
        assert completed_col.filter_type == "select"
        assert completed_col.filter_options == [
            {"value": "true", "label": "Yes"},
            {"value": "false", "label": "No"},
        ]

    def test_text_field_filter_type_text(self) -> None:
        ux = ir.UXSpec(filter=["title"])
        surface = _list_surface(ux=ux, field_names=["title"])
        entity = _task_entity()

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        title_col = next(c for c in ctx.table.columns if c.key == "title")
        assert title_col.filter_type == "text"
        assert title_col.filter_options == []


# ---------------------------------------------------------------------------
# Tests — TableContext fields from UXSpec
# ---------------------------------------------------------------------------


class TestTableContextFromUX:
    """TableContext should get sort defaults, search fields, empty message, and table ID."""

    def test_table_context_gets_sort_defaults(self) -> None:
        ux = ir.UXSpec(sort=[ir.SortSpec(field="title", direction="desc")])
        surface = _list_surface(ux=ux)
        entity = _task_entity()

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        assert ctx.table.default_sort_field == "title"
        assert ctx.table.default_sort_dir == "desc"
        assert ctx.table.sort_field == "title"
        assert ctx.table.sort_dir == "desc"

    def test_table_context_gets_search_fields(self) -> None:
        ux = ir.UXSpec(search=["title"])
        surface = _list_surface(ux=ux)
        entity = _task_entity()

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        assert ctx.table.search_fields == ["title"]
        assert ctx.table.search_enabled is True

    def test_table_context_gets_empty_message(self) -> None:
        ux = ir.UXSpec(empty_message="No tasks yet. Create one!")
        surface = _list_surface(ux=ux)
        entity = _task_entity()

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        assert ctx.table.empty_message == "No tasks yet. Create one!"

    def test_table_context_gets_table_id(self) -> None:
        surface = _list_surface()
        entity = _task_entity()

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        assert ctx.table.table_id == "dt-task_list"

    def test_search_first_sets_flag(self) -> None:
        ux = ir.UXSpec(search_first=True, search=["title"])
        surface = _list_surface(ux=ux)
        entity = _task_entity()

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        assert ctx.table.search_first is True

    def test_search_first_default_empty_message(self) -> None:
        ux = ir.UXSpec(search_first=True, search=["title"])
        surface = _list_surface(ux=ux)
        entity = _task_entity()

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        assert (
            "search" in ctx.table.empty_message.lower()
            or "filter" in ctx.table.empty_message.lower()
        )

    def test_search_first_custom_empty_message(self) -> None:
        ux = ir.UXSpec(search_first=True, search=["title"], empty_message="Search for employees.")
        surface = _list_surface(ux=ux)
        entity = _task_entity()

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        assert ctx.table.empty_message == "Search for employees."

    def test_search_first_false_by_default(self) -> None:
        ux = ir.UXSpec(search=["title"])
        surface = _list_surface(ux=ux)
        entity = _task_entity()

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        assert ctx.table.search_first is False


# ---------------------------------------------------------------------------
# Tests — backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    """Surfaces without a ux block should produce sensible defaults."""

    def test_backward_compat_no_ux(self) -> None:
        surface = _list_surface(ux=None)
        entity = _task_entity()

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        assert ctx.table.default_sort_field == ""
        assert ctx.table.default_sort_dir == "asc"
        assert ctx.table.search_fields == []
        assert ctx.table.empty_message == "No items found."
        assert ctx.table.filter_values == {}
        assert ctx.table.table_id == "dt-task_list"
        for col in ctx.table.columns:
            assert col.sortable is False
            assert col.filterable is False

    def test_backward_compat_no_entity(self) -> None:
        surface = _list_surface(ux=None)

        ctx = compile_surface_to_context(surface, None)

        assert ctx.table is not None
        assert ctx.table.entity_name == "Task"
        assert ctx.table.table_id == "dt-task_list"


# ---------------------------------------------------------------------------
# Tests — sensitive field handling
# ---------------------------------------------------------------------------


class TestSensitiveColumn:
    """Sensitive fields should be masked in list views and excluded from filters."""

    def _employee_entity(self) -> ir.EntitySpec:
        """Build Employee entity with a sensitive field."""
        return ir.EntitySpec(
            name="Employee",
            title="Employee",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="name",
                    type=ir.FieldType(kind=FieldTypeKind.STR, max_length=200),
                    modifiers=[FieldModifier.REQUIRED],
                ),
                ir.FieldSpec(
                    name="bank_account",
                    type=ir.FieldType(kind=FieldTypeKind.STR, max_length=8),
                    modifiers=[FieldModifier.SENSITIVE],
                ),
            ],
        )

    def _employee_surface(self, ux: ir.UXSpec | None = None) -> ir.SurfaceSpec:
        return ir.SurfaceSpec(
            name="employee_list",
            title="Employees",
            entity_ref="Employee",
            mode=SurfaceMode.LIST,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    title="Main",
                    elements=[
                        ir.SurfaceElement(field_name="name", label="Name"),
                        ir.SurfaceElement(field_name="bank_account", label="Bank Account"),
                    ],
                )
            ],
            actions=[],
            ux=ux,
        )

    def test_sensitive_column_type(self) -> None:
        """Sensitive fields should get column type 'sensitive'."""
        surface = self._employee_surface()
        entity = self._employee_entity()

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        cols_by_key = {c.key: c for c in ctx.table.columns}
        assert cols_by_key["bank_account"].type == "sensitive"
        assert cols_by_key["name"].type == "text"

    def test_sensitive_column_not_filterable(self) -> None:
        """Sensitive fields should not be filterable even if ux.filter requests it."""
        ux = ir.UXSpec(filter=["name", "bank_account"])
        surface = self._employee_surface(ux=ux)
        entity = self._employee_entity()

        ctx = compile_surface_to_context(surface, entity)

        assert ctx.table is not None
        cols_by_key = {c.key: c for c in ctx.table.columns}
        assert cols_by_key["name"].filterable is True
        assert cols_by_key["bank_account"].filterable is False


# ---------------------------------------------------------------------------
# Tests — DSL parse round-trip for search_first
# ---------------------------------------------------------------------------


class TestSearchFirstParse:
    """Verify search_first: true/false is parsed from DSL."""

    def test_parse_search_first_true(self) -> None:
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl

        dsl = """\
module test_app
app test "Test"

entity Employee "Employee":
  id: uuid pk
  name: str(200)
  job_title: str(200)

surface employee_list "Employees":
  uses entity Employee
  mode: list
  section main:
    field name "Name"
    field job_title "Title"
  ux:
    search_first: true
    search: name, job_title
    empty: "Search for employees."
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        surface = fragment.surfaces[0]
        assert surface.ux is not None
        assert surface.ux.search_first is True
        assert surface.ux.search == ["name", "job_title"]
        assert surface.ux.empty_message == "Search for employees."

    def test_parse_search_first_false(self) -> None:
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl

        dsl = """\
module test_app
app test "Test"

entity Task "Task":
  id: uuid pk
  title: str(200)

surface task_list "Tasks":
  uses entity Task
  mode: list
  section main:
    field title "Title"
  ux:
    search_first: false
    search: title
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        surface = fragment.surfaces[0]
        assert surface.ux is not None
        assert surface.ux.search_first is False

    def test_parse_no_search_first_defaults_false(self) -> None:
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl

        dsl = """\
module test_app
app test "Test"

entity Task "Task":
  id: uuid pk
  title: str(200)

surface task_list "Tasks":
  uses entity Task
  mode: list
  section main:
    field title "Title"
  ux:
    search: title
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        surface = fragment.surfaces[0]
        assert surface.ux is not None
        assert surface.ux.search_first is False
