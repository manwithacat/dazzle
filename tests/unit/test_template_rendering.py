"""
Unit tests for the template rendering pipeline.

Tests the pure-function rendering: template compiler, Jinja2 renderer,
custom filters, design token CSS, and mock data generation — no server needed.
"""

from __future__ import annotations

from datetime import date

import pytest

from dazzle.core.ir import (
    AppSpec,
    DomainSpec,
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
    SurfaceElement,
    SurfaceMode,
    SurfaceSection,
    SurfaceSpec,
)

# These modules are part of the HTMX template runtime and may not be
# installed in every CI configuration (they live in unpackaged source).
pytest.importorskip("dazzle_dnr_ui.converters.template_compiler")
pytest.importorskip("dazzle_dnr_ui.runtime.template_renderer")

from dazzle_dnr_ui.converters.template_compiler import (  # noqa: E402
    compile_appspec_to_templates,
    compile_surface_to_context,
)
from dazzle_dnr_ui.runtime.mock_data import generate_mock_records  # noqa: E402
from dazzle_dnr_ui.runtime.template_context import (  # noqa: E402
    ColumnContext,
    DetailContext,
    FieldContext,
    FormContext,
    NavItemContext,
    PageContext,
    TableContext,
)
from dazzle_dnr_ui.runtime.template_renderer import (  # noqa: E402
    create_jinja_env,
    render_fragment,
    render_page,
)
from dazzle_dnr_ui.themes.token_compiler import (  # noqa: E402
    compile_design_tokens,
    tokens_to_css,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _task_entity() -> EntitySpec:
    """Build a minimal Task entity for tests."""
    return EntitySpec(
        name="Task",
        title="Task",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind=FieldTypeKind.STR, max_length=200),
                modifiers=[FieldModifier.REQUIRED],
            ),
            FieldSpec(
                name="completed",
                type=FieldType(kind=FieldTypeKind.BOOL),
                default=False,
            ),
            FieldSpec(
                name="due_date",
                type=FieldType(kind=FieldTypeKind.DATE),
            ),
            FieldSpec(
                name="priority",
                type=FieldType(
                    kind=FieldTypeKind.ENUM,
                    enum_values=["low", "medium", "high"],
                ),
            ),
            FieldSpec(
                name="amount",
                type=FieldType(kind=FieldTypeKind.MONEY, currency_code="GBP"),
            ),
        ],
    )


def _list_surface() -> SurfaceSpec:
    return SurfaceSpec(
        name="task_list",
        title="Tasks",
        entity_ref="Task",
        mode=SurfaceMode.LIST,
        sections=[
            SurfaceSection(
                name="main",
                title="Main",
                elements=[
                    SurfaceElement(field_name="title", label="Title"),
                    SurfaceElement(field_name="completed", label="Done"),
                    SurfaceElement(field_name="priority", label="Priority"),
                ],
            )
        ],
    )


def _create_surface() -> SurfaceSpec:
    return SurfaceSpec(
        name="task_create",
        title="Create Task",
        entity_ref="Task",
        mode=SurfaceMode.CREATE,
        sections=[
            SurfaceSection(
                name="main",
                title="Main",
                elements=[
                    SurfaceElement(field_name="title", label="Title"),
                    SurfaceElement(field_name="completed", label="Done"),
                ],
            )
        ],
    )


def _edit_surface() -> SurfaceSpec:
    return SurfaceSpec(
        name="task_edit",
        title="Edit Task",
        entity_ref="Task",
        mode=SurfaceMode.EDIT,
        sections=[
            SurfaceSection(
                name="main",
                title="Main",
                elements=[
                    SurfaceElement(field_name="title", label="Title"),
                    SurfaceElement(field_name="completed", label="Done"),
                ],
            )
        ],
    )


def _view_surface() -> SurfaceSpec:
    return SurfaceSpec(
        name="task_view",
        title="Task Details",
        entity_ref="Task",
        mode=SurfaceMode.VIEW,
        sections=[
            SurfaceSection(
                name="main",
                title="Main",
                elements=[
                    SurfaceElement(field_name="title", label="Title"),
                    SurfaceElement(field_name="completed", label="Done"),
                ],
            )
        ],
    )


# ===================================================================
# 1. compile_surface_to_context tests
# ===================================================================


class TestCompileSurfaceToContext:
    """Tests for compile_surface_to_context across all surface modes."""

    def test_list_mode_produces_table_context(self) -> None:
        ctx = compile_surface_to_context(_list_surface(), _task_entity())

        assert ctx.table is not None
        assert ctx.form is None
        assert ctx.detail is None
        assert ctx.template == "components/filterable_table.html"
        assert ctx.page_title == "Tasks"
        assert ctx.table.entity_name == "Task"
        assert ctx.table.api_endpoint == "/tasks"
        assert ctx.table.create_url == "/task/create"
        assert len(ctx.table.columns) == 3
        col_keys = [c.key for c in ctx.table.columns]
        assert col_keys == ["title", "completed", "priority"]

    def test_list_column_types(self) -> None:
        ctx = compile_surface_to_context(_list_surface(), _task_entity())
        col_map = {c.key: c.type for c in ctx.table.columns}
        assert col_map["title"] == "text"
        assert col_map["completed"] == "bool"
        assert col_map["priority"] == "badge"

    def test_create_mode_produces_form_context(self) -> None:
        ctx = compile_surface_to_context(_create_surface(), _task_entity())

        assert ctx.form is not None
        assert ctx.table is None
        assert ctx.template == "components/form.html"
        assert ctx.form.mode == "create"
        assert ctx.form.method == "post"
        assert ctx.form.action_url == "/tasks"
        assert len(ctx.form.fields) == 2

    def test_edit_mode_produces_form_context(self) -> None:
        ctx = compile_surface_to_context(_edit_surface(), _task_entity())

        assert ctx.form is not None
        assert ctx.form.mode == "edit"
        assert ctx.form.method == "put"
        assert "{id}" in ctx.form.action_url

    def test_view_mode_produces_detail_context(self) -> None:
        ctx = compile_surface_to_context(_view_surface(), _task_entity())

        assert ctx.detail is not None
        assert ctx.form is None
        assert ctx.template == "components/detail_view.html"
        assert ctx.detail.entity_name == "Task"
        assert ctx.detail.edit_url is not None
        assert "{id}" in ctx.detail.edit_url

    def test_create_form_field_types(self) -> None:
        """Form fields should map IR types to HTML input types."""
        surface = SurfaceSpec(
            name="task_create_full",
            title="Create Task",
            entity_ref="Task",
            mode=SurfaceMode.CREATE,
            sections=[
                SurfaceSection(
                    name="main",
                    title="Main",
                    elements=[
                        SurfaceElement(field_name="title"),
                        SurfaceElement(field_name="completed"),
                        SurfaceElement(field_name="due_date"),
                        SurfaceElement(field_name="priority"),
                        SurfaceElement(field_name="amount"),
                    ],
                )
            ],
        )
        ctx = compile_surface_to_context(surface, _task_entity())
        field_map = {f.name: f.type for f in ctx.form.fields}
        assert field_map["title"] == "text"
        assert field_map["completed"] == "checkbox"
        assert field_map["due_date"] == "date"
        assert field_map["priority"] == "select"
        assert field_map["amount"] == "number"

    def test_enum_field_has_options(self) -> None:
        surface = SurfaceSpec(
            name="t",
            title="T",
            entity_ref="Task",
            mode=SurfaceMode.CREATE,
            sections=[
                SurfaceSection(
                    name="main",
                    title="Main",
                    elements=[SurfaceElement(field_name="priority")],
                )
            ],
        )
        ctx = compile_surface_to_context(surface, _task_entity())
        priority_field = ctx.form.fields[0]
        assert priority_field.type == "select"
        assert len(priority_field.options) == 3
        values = [o["value"] for o in priority_field.options]
        assert "low" in values
        assert "high" in values

    def test_required_flag_propagated(self) -> None:
        ctx = compile_surface_to_context(_create_surface(), _task_entity())
        title_field = next(f for f in ctx.form.fields if f.name == "title")
        done_field = next(f for f in ctx.form.fields if f.name == "completed")
        assert title_field.required is True
        assert done_field.required is False

    def test_no_entity_falls_back(self) -> None:
        surface = SurfaceSpec(
            name="orphan",
            title="Orphan",
            entity_ref="Widget",
            mode=SurfaceMode.LIST,
        )
        ctx = compile_surface_to_context(surface, None)
        assert ctx.table is not None
        assert ctx.table.entity_name == "Widget"


# ===================================================================
# 2. render_page / render_fragment tests
# ===================================================================


class TestRendering:
    """Tests for render_page and render_fragment."""

    def _make_list_page_context(self) -> PageContext:
        return PageContext(
            page_title="Tasks",
            app_name="Test App",
            template="components/filterable_table.html",
            nav_items=[
                NavItemContext(label="Tasks", route="/task", active=True),
            ],
            table=TableContext(
                entity_name="Task",
                title="Tasks",
                columns=[
                    ColumnContext(key="title", label="Title"),
                    ColumnContext(key="completed", label="Done", type="bool"),
                ],
                api_endpoint="/tasks",
                create_url="/task/create",
                detail_url_template="/task/{id}",
                rows=[
                    {"id": "1", "title": "Write tests", "completed": True},
                    {"id": "2", "title": "Fix bug", "completed": False},
                ],
                total=2,
            ),
        )

    def test_render_page_produces_full_html(self) -> None:
        html = render_page(self._make_list_page_context())

        assert "<!DOCTYPE html>" in html or "<!doctype html>" in html.lower()
        assert "<html" in html
        assert "</html>" in html
        assert "<nav" in html or "navbar" in html.lower()
        assert "Tasks" in html

    def test_render_page_contains_table(self) -> None:
        html = render_page(self._make_list_page_context())
        assert "<table" in html or "hx-get" in html

    def test_render_page_contains_nav(self) -> None:
        html = render_page(self._make_list_page_context())
        assert "Tasks" in html

    def test_render_page_contains_htmx(self) -> None:
        """Rendered pages should include HTMX attributes or script."""
        html = render_page(self._make_list_page_context())
        assert "hx-" in html or "htmx" in html.lower()

    def test_render_fragment_no_layout(self) -> None:
        """Fragments should NOT include DOCTYPE or full layout."""
        fragment = render_fragment(
            "fragments/table_rows.html",
            table=TableContext(
                entity_name="Task",
                title="Tasks",
                columns=[ColumnContext(key="title", label="Title")],
                api_endpoint="/tasks",
                detail_url_template="/task/{id}",
                rows=[{"id": "1", "title": "Hello"}],
                total=1,
            ),
        )
        assert "<!DOCTYPE" not in fragment
        assert "<html" not in fragment
        # Should contain row markup
        assert "<tr" in fragment or "title" in fragment.lower()

    def test_render_form_page(self) -> None:
        ctx = PageContext(
            page_title="Create Task",
            app_name="Test App",
            template="components/form.html",
            form=FormContext(
                entity_name="Task",
                title="Create Task",
                fields=[
                    FieldContext(name="title", label="Title", type="text", required=True),
                ],
                action_url="/tasks",
                method="post",
                mode="create",
            ),
        )
        html = render_page(ctx)
        assert "<form" in html
        assert "<input" in html or "title" in html.lower()

    def test_render_detail_page(self) -> None:
        ctx = PageContext(
            page_title="Task Details",
            app_name="Test App",
            template="components/detail_view.html",
            detail=DetailContext(
                entity_name="Task",
                title="Task Details",
                fields=[
                    FieldContext(name="title", label="Title"),
                ],
                item={"title": "My Task"},
                edit_url="/task/1/edit",
                back_url="/task",
            ),
        )
        html = render_page(ctx)
        assert "My Task" in html or "Task Details" in html


# ===================================================================
# 3. Jinja2 custom filter tests
# ===================================================================


class TestJinjaFilters:
    """Tests for custom Jinja2 filters."""

    @pytest.fixture()
    def env(self):
        return create_jinja_env()

    def test_currency_filter_gbp(self, env) -> None:
        tmpl = env.from_string("{{ val|currency }}")
        assert tmpl.render(val=42.5) == "£42.50"

    def test_currency_filter_usd(self, env) -> None:
        tmpl = env.from_string("{{ val|currency('USD') }}")
        assert tmpl.render(val=100) == "$100.00"

    def test_currency_filter_none(self, env) -> None:
        tmpl = env.from_string("{{ val|currency }}")
        assert tmpl.render(val=None) == ""

    def test_dateformat_filter_date(self, env) -> None:
        tmpl = env.from_string("{{ val|dateformat }}")
        d = date(2025, 3, 15)
        result = tmpl.render(val=d)
        assert "15" in result
        assert "Mar" in result
        assert "2025" in result

    def test_dateformat_filter_iso_string(self, env) -> None:
        tmpl = env.from_string("{{ val|dateformat }}")
        result = tmpl.render(val="2025-06-01T10:00:00")
        assert "01" in result
        assert "Jun" in result

    def test_badge_class_active(self, env) -> None:
        tmpl = env.from_string("{{ val|badge_class }}")
        assert "badge-success" in tmpl.render(val="active")

    def test_badge_class_pending(self, env) -> None:
        tmpl = env.from_string("{{ val|badge_class }}")
        assert "badge-warning" in tmpl.render(val="pending")

    def test_badge_class_unknown(self, env) -> None:
        tmpl = env.from_string("{{ val|badge_class }}")
        assert "badge-ghost" in tmpl.render(val="xyz")

    def test_bool_icon_true(self, env) -> None:
        # Use |safe since bool_icon returns raw HTML (autoescaped by Jinja2)
        tmpl = env.from_string("{{ val|bool_icon|safe }}")
        result = tmpl.render(val=True)
        assert "text-success" in result
        assert "✓" in result or "&#10003;" in result

    def test_bool_icon_false(self, env) -> None:
        tmpl = env.from_string("{{ val|bool_icon|safe }}")
        result = tmpl.render(val=False)
        assert "✗" in result or "&#10005;" in result

    def test_truncate_text(self, env) -> None:
        tmpl = env.from_string("{{ val|truncate_text(10) }}")
        assert tmpl.render(val="short") == "short"
        result = tmpl.render(val="a very long string here")
        assert result.endswith("...")
        assert len(result) == 13  # 10 chars + "..."

    def test_truncate_text_none(self, env) -> None:
        tmpl = env.from_string("{{ val|truncate_text }}")
        assert tmpl.render(val=None) == ""


# ===================================================================
# 4. Design token CSS tests
# ===================================================================


class TestDesignTokens:
    """Tests for tokens_to_css and compile_design_tokens."""

    def test_tokens_to_css_produces_root_block(self) -> None:
        tokens = {"primary": "#3b82f6", "space-md": "1rem"}
        css = tokens_to_css(tokens)
        assert css.startswith(":root {")
        assert css.endswith("}")
        assert "--dz-primary: #3b82f6;" in css
        assert "--dz-space-md: 1rem;" in css

    def test_tokens_to_css_empty(self) -> None:
        css = tokens_to_css({})
        assert ":root {" in css

    def test_compile_design_tokens_defaults(self) -> None:
        tokens = compile_design_tokens()
        # Should have spacing, density, tone, and palette keys
        assert "space-md" in tokens
        assert "row-height" in tokens
        assert "radius" in tokens
        assert "primary" in tokens

    def test_compile_design_tokens_compact_purple(self) -> None:
        tokens = compile_design_tokens(spacing="compact", palette="purple")
        assert tokens["space-md"] == "0.5rem"  # compact spacing
        assert tokens["primary"] == "#8b5cf6"  # purple palette

    def test_all_axis_combinations_valid(self) -> None:
        """Every valid axis combination should produce tokens without error."""
        for spacing in ("compact", "normal", "relaxed"):
            for density in ("data-heavy", "balanced", "spacious"):
                for tone in ("corporate", "friendly", "minimal"):
                    for palette in ("blue", "green", "purple", "neutral"):
                        tokens = compile_design_tokens(
                            spacing=spacing,
                            density=density,
                            tone=tone,
                            palette=palette,
                        )
                        assert len(tokens) > 0


# ===================================================================
# 5. Mock data generation tests
# ===================================================================


class TestMockData:
    """Tests for generate_mock_records."""

    def test_generates_correct_count(self) -> None:
        records = generate_mock_records(_task_entity(), count=7)
        assert len(records) == 7

    def test_all_fields_present(self) -> None:
        records = generate_mock_records(_task_entity(), count=1)
        record = records[0]
        for field in _task_entity().fields:
            assert field.name in record, f"Missing field: {field.name}"

    def test_uuid_pk_is_string(self) -> None:
        records = generate_mock_records(_task_entity(), count=1)
        assert isinstance(records[0]["id"], str)
        assert len(records[0]["id"]) == 36  # UUID format

    def test_bool_field_is_bool(self) -> None:
        records = generate_mock_records(_task_entity(), count=1)
        assert isinstance(records[0]["completed"], bool)

    def test_enum_values_from_spec(self) -> None:
        records = generate_mock_records(_task_entity(), count=10)
        valid = {"low", "medium", "high"}
        for r in records:
            assert r["priority"] in valid

    def test_date_field_is_iso_string(self) -> None:
        records = generate_mock_records(_task_entity(), count=1)
        due = records[0]["due_date"]
        # Should parse as a date
        date.fromisoformat(due)

    def test_money_field_is_numeric(self) -> None:
        records = generate_mock_records(_task_entity(), count=1)
        assert isinstance(records[0]["amount"], float)


# ===================================================================
# 6. compile_appspec_to_templates integration
# ===================================================================


class TestCompileAppSpec:
    """Tests for compile_appspec_to_templates."""

    def _make_appspec(self) -> AppSpec:
        entity = _task_entity()
        return AppSpec(
            name="test_app",
            title="Test App",
            domain=DomainSpec(entities=[entity]),
            surfaces=[
                _list_surface(),
                _create_surface(),
                _view_surface(),
            ],
        )

    def test_produces_route_map(self) -> None:
        contexts = compile_appspec_to_templates(self._make_appspec())
        assert isinstance(contexts, dict)
        assert len(contexts) >= 3  # list, create, view + maybe root

    def test_root_route_assigned(self) -> None:
        contexts = compile_appspec_to_templates(self._make_appspec())
        assert "/" in contexts

    def test_list_route(self) -> None:
        contexts = compile_appspec_to_templates(self._make_appspec())
        assert "/task" in contexts
        assert contexts["/task"].table is not None

    def test_create_route(self) -> None:
        contexts = compile_appspec_to_templates(self._make_appspec())
        assert "/task/create" in contexts
        assert contexts["/task/create"].form is not None

    def test_app_name_injected(self) -> None:
        contexts = compile_appspec_to_templates(self._make_appspec())
        for ctx in contexts.values():
            assert ctx.app_name == "Test App"
