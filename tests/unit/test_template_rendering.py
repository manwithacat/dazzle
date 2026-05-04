"""
Unit tests for the template rendering pipeline.

Tests the pure-function rendering: template compiler, Jinja2 renderer,
custom filters, design token CSS, and mock data generation — no server needed.
"""

from datetime import date, datetime, timedelta

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
pytest.importorskip("dazzle_ui.converters.template_compiler")
pytest.importorskip("dazzle_ui.runtime.template_renderer")

from dazzle_ui.converters.template_compiler import (  # noqa: E402
    compile_appspec_to_templates,
    compile_surface_to_context,
)
from dazzle_ui.runtime.mock_data import generate_mock_records  # noqa: E402
from dazzle_ui.runtime.template_context import (  # noqa: E402
    ColumnContext,
    DetailContext,
    FieldContext,
    FormContext,
    NavItemContext,
    PageContext,
    TableContext,
)
from dazzle_ui.runtime.template_renderer import (  # noqa: E402
    create_jinja_env,
    render_fragment,
    render_page,
)
from dazzle_ui.themes.token_compiler import (  # noqa: E402
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

    def test_detail_context_has_api_endpoint(self) -> None:
        """DetailContext must have api_endpoint with {id} for data fetching (#478)."""
        ctx = compile_surface_to_context(_view_surface(), _task_entity())

        assert ctx.detail is not None
        assert ctx.detail.api_endpoint is not None
        assert "{id}" in ctx.detail.api_endpoint

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
        # Money fields emit a single "money" type widget
        assert field_map["amount"] == "money"

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

    def test_nav_links_use_fragment_targeting(self) -> None:
        """Nav links should target #main-content with view transitions and preload."""
        html = render_page(self._make_list_page_context())
        assert 'hx-target="#main-content"' in html
        # v0.61.18 (#876) extended the swap string to scroll #main-content
        # to top on morph; substring check survives future suffix changes.
        assert 'hx-swap="morph:innerHTML transition:true' in html
        assert 'hx-push-url="true"' in html
        assert 'preload="mousedown"' in html

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

    def test_render_page_content_only(self) -> None:
        """content_only=True returns just the content template, no layout."""
        html = render_page(self._make_list_page_context(), content_only=True)
        # Should NOT include layout elements
        assert "<!DOCTYPE" not in html
        assert "<html" not in html
        assert "<nav" not in html
        # Should still contain the content (table markup)
        assert "<table" in html or "hx-get" in html

    def test_render_page_content_only_vs_full(self) -> None:
        """content_only output should be a subset of the full page output."""
        ctx = self._make_list_page_context()
        full = render_page(ctx)
        content_only = render_page(ctx, content_only=True)
        # Content-only should be shorter than full page
        assert len(content_only) < len(full)
        # Full page should have layout elements that content_only lacks
        assert "<!DOCTYPE" in full
        assert "<!DOCTYPE" not in content_only
        assert "<html" not in content_only

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

    def test_render_table_rows_empty_columns(self) -> None:
        """Table rows with empty columns should not crash (issue #270)."""
        fragment = render_fragment(
            "fragments/table_rows.html",
            table=TableContext(
                entity_name="Task",
                title="Tasks",
                columns=[],
                api_endpoint="/tasks",
                detail_url_template="/task/{id}",
                rows=[{"id": "1", "title": "Hello"}],
                total=1,
            ),
        )
        assert "<tr" in fragment
        # Should fall back to item.id for accessibility labels
        assert "1" in fragment

    def test_render_table_rows_ref_column_displays_name(self) -> None:
        """Ref columns should display resolved name, not raw dict repr (#308)."""
        fragment = render_fragment(
            "fragments/table_rows.html",
            table=TableContext(
                entity_name="QualityCheck",
                title="Quality Checks",
                columns=[
                    ColumnContext(key="title", label="Title"),
                    ColumnContext(key="checked_by", label="Checked By", type="ref"),
                ],
                api_endpoint="/qualitychecks",
                detail_url_template="/qualitycheck/{id}",
                rows=[
                    {
                        "id": "1",
                        "title": "Review A",
                        "checked_by": {
                            "id": "c-123",
                            "name": "Jane Smith",
                            "email": "jane@example.com",
                        },
                    }
                ],
                total=1,
            ),
        )
        assert "Jane Smith" in fragment
        # Must NOT contain raw dict repr
        assert "{'id'" not in fragment
        assert "c-123" not in fragment  # Should show name, not id

    def test_render_table_rows_ref_column_fallback_to_email(self) -> None:
        """Ref columns without name/title should fall back to email."""
        fragment = render_fragment(
            "fragments/table_rows.html",
            table=TableContext(
                entity_name="Task",
                title="Tasks",
                columns=[
                    ColumnContext(key="assigned_to", label="Assigned To", type="ref"),
                ],
                api_endpoint="/tasks",
                detail_url_template="/task/{id}",
                rows=[
                    {
                        "id": "1",
                        "assigned_to": {"id": "u-456", "email": "bob@example.com"},
                    }
                ],
                total=1,
            ),
        )
        assert "bob@example.com" in fragment
        assert "{'id'" not in fragment

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

    def test_render_page_partial(self) -> None:
        """partial=True omits the HTML/HEAD wrapper."""
        html = render_page(self._make_list_page_context(), partial=True)
        assert "<!DOCTYPE" not in html
        assert "<html" not in html
        # But content is still rendered
        assert "<table" in html or "hx-get" in html

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

    @pytest.mark.parametrize(
        ("template", "value", "expected"),
        [
            # Values are stored in minor units (pence/cents).
            ("{{ val|currency }}", 4250, "£42.50"),
            ("{{ val|currency('USD') }}", 10000, "$100.00"),
            ("{{ val|currency }}", None, ""),
            ("{{ val|currency }}", "not-a-number", "not-a-number"),  # non-numeric → str()
        ],
        ids=["gbp", "usd", "none", "non_numeric"],
    )
    def test_currency_filter(self, env, template, value, expected) -> None:
        tmpl = env.from_string(template)
        assert tmpl.render(val=value) == expected

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

    def test_bool_icon_true(self, env) -> None:
        # Use |safe since bool_icon returns raw HTML (autoescaped by Jinja2)
        tmpl = env.from_string("{{ val|bool_icon|safe }}")
        result = tmpl.render(val=True)
        assert "text-[hsl(var(--success))]" in result
        assert "✓" in result or "&#10003;" in result

    def test_bool_icon_false(self, env) -> None:
        tmpl = env.from_string("{{ val|bool_icon|safe }}")
        result = tmpl.render(val=False)
        assert "text-[hsl(var(--muted-foreground)/0.3)]" in result
        assert "✗" in result or "&#10005;" in result

    def test_truncate_text(self, env) -> None:
        """Length-truncation behaviour with the tail ellipsis."""
        tmpl = env.from_string("{{ val|truncate_text(10) }}")
        assert tmpl.render(val="short") == "short"
        result = tmpl.render(val="a very long string here")
        assert result.endswith("...")
        assert len(result) == 13  # 10 chars + "..."

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, ""),
            # FK ref dicts should display a name, not Python repr (#308).
            ({"id": "abc-123", "name": "John Doe", "email": "john@test.com"}, "John Doe"),
            ({"id": "abc-123", "title": "My Company"}, "My Company"),
            ({"id": "abc-123", "email": "user@example.com"}, "user@example.com"),
            ({"id": "abc-123"}, "abc-123"),  # falls back to id
            ({}, ""),
        ],
        ids=[
            "none",
            "dict_with_name",
            "dict_falls_back_to_title",
            "dict_falls_back_to_email",
            "dict_falls_back_to_id",
            "empty_dict",
        ],
    )
    def test_truncate_text_value_resolution(self, env, value, expected) -> None:
        """Resolution order for non-string inputs (#308)."""
        tmpl = env.from_string("{{ val|truncate_text }}")
        assert tmpl.render(val=value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, ""),
            ("not-a-date", "not-a-date"),  # unparseable string returns raw
            (42, "42"),  # non-date types fall through to str()
        ],
        ids=["none", "invalid_string", "non_date_type"],
    )
    def test_dateformat_filter_passthrough(self, env, value, expected) -> None:
        """dateformat returns str(val) when the value can't be parsed."""
        tmpl = env.from_string("{{ val|dateformat }}")
        assert tmpl.render(val=value) == expected

    def test_dateformat_filter_datetime(self, env) -> None:
        tmpl = env.from_string("{{ val|dateformat }}")
        dt = datetime(2025, 12, 25, 10, 30, 0)
        result = tmpl.render(val=dt)
        assert "25" in result
        assert "Dec" in result

    # --- badge_tone filter (cycle 238, closes part of EX-041 status-badge
    # drift). Exercises the canonical semantic tone resolver used by the
    # `render_status_badge` macro. ---

    @pytest.mark.parametrize(
        ("states", "expected_tone"),
        [
            (("active", "done", "completed", "approved", "resolved", "passed"), "success"),
            (("in_progress", "open", "running", "processing"), "info"),
            (
                ("review", "pending", "on_hold", "waiting", "blocked", "high", "major"),
                "warning",
            ),
            (
                (
                    "inactive",
                    "overdue",
                    "cancelled",
                    "rejected",
                    "failed",
                    "critical",
                    "urgent",
                ),
                "destructive",
            ),
            (
                ("todo", "draft", "new", "backlog", "low", "minor", "unknown_value"),
                "neutral",
            ),
            ((None,), "neutral"),  # None defaults to neutral
        ],
        ids=["success", "info", "warning", "destructive", "neutral_fallback", "none"],
    )
    def test_badge_tone_states(self, env, states, expected_tone) -> None:
        """Each tone has a canonical state-name set; cycle 238, EX-041."""
        tmpl = env.from_string("{{ val|badge_tone }}")
        for val in states:
            assert tmpl.render(val=val) == expected_tone, f"{val} should map to {expected_tone}"

    @pytest.mark.parametrize(
        ("value", "expected_tone"),
        [
            ("ACTIVE", "success"),  # uppercase normalises to success
            ("In Progress", "info"),  # space-to-underscore
        ],
        ids=["uppercase", "space_to_underscore"],
    )
    def test_badge_tone_normalisation(self, env, value, expected_tone) -> None:
        tmpl = env.from_string("{{ val|badge_tone }}")
        assert tmpl.render(val=value) == expected_tone

    # --- status_badge macro (cycle 238) ---
    # The macro is the canonical renderer for every enum/state field across
    # the template set. Replaces ~16 inline class-combination call sites that
    # had drifted into 7 distinct wrapper styles.

    def test_status_badge_macro_happy_path(self, env) -> None:
        tmpl = env.from_string(
            "{% from 'macros/status_badge.html' import render_status_badge %}"
            "{{ render_status_badge(value='in_progress') }}"
        )
        out = tmpl.render()
        assert "dz-badge" in out
        assert 'data-dz-tone="info"' in out
        assert "In Progress" in out  # humanised
        assert 'role="status"' in out
        assert "aria-label=" in out

    def test_status_badge_macro_none_renders_placeholder(self, env) -> None:
        tmpl = env.from_string(
            "{% from 'macros/status_badge.html' import render_status_badge %}"
            "{{ render_status_badge(value=None) }}"
        )
        out = tmpl.render()
        assert "—" in out
        # No active badge when value is None — only the dz-badge-empty
        # placeholder span. Match on `dz-badge"` (closing quote) so the
        # empty-placeholder substring doesn't trigger the negative.
        assert 'dz-badge"' not in out
        assert "data-dz-tone" not in out

    def test_status_badge_macro_tone_override(self, env) -> None:
        tmpl = env.from_string(
            "{% from 'macros/status_badge.html' import render_status_badge %}"
            "{{ render_status_badge(value='anything', tone='destructive') }}"
        )
        out = tmpl.render()
        assert 'data-dz-tone="destructive"' in out

    def test_status_badge_macro_size_sm(self, env) -> None:
        """Post-CSS-refactor: sizing routes via the .dz-badge-sm
        modifier class instead of inline Tailwind text-[10px]/h-4.
        Visual contract is preserved by components/badge.css; the
        template just emits the modifier."""
        tmpl = env.from_string(
            "{% from 'macros/status_badge.html' import render_status_badge %}"
            "{{ render_status_badge(value='done', size='sm') }}"
        )
        out = tmpl.render()
        assert "dz-badge-sm" in out

    def test_status_badge_macro_md_default(self, env) -> None:
        """Post-CSS-refactor: md is the default — no modifier class
        needed. The .dz-badge base rule provides md sizing."""
        tmpl = env.from_string(
            "{% from 'macros/status_badge.html' import render_status_badge %}"
            "{{ render_status_badge(value='done') }}"
        )
        out = tmpl.render()
        assert "dz-badge" in out
        # No size modifier — base class is implicitly md
        assert "dz-badge-sm" not in out

    def test_status_badge_macro_bordered(self, env) -> None:
        """Post-CSS-refactor: bordered routes via the .bordered
        modifier class. Tone colour inheritance happens in
        components/badge.css via .dz-badge.bordered[data-dz-tone='...']."""
        tmpl = env.from_string(
            "{% from 'macros/status_badge.html' import render_status_badge %}"
            "{{ render_status_badge(value='done', bordered=true) }}"
        )
        out = tmpl.render()
        assert "bordered" in out
        assert 'data-dz-tone="success"' in out

    def test_status_badge_macro_display_override(self, env) -> None:
        tmpl = env.from_string(
            "{% from 'macros/status_badge.html' import render_status_badge %}"
            "{{ render_status_badge(value='open', display='New!') }}"
        )
        out = tmpl.render()
        assert ">New!<" in out

    def test_status_badge_macro_uses_data_attribute_tones(self, env) -> None:
        """Post-CSS-refactor: tone routes via data-dz-tone attribute,
        not inline hsl(var(--token)) classes. Component CSS in
        components/badge.css owns the colour mapping. Tested at the
        attribute level here; the actual hsl tokens are pinned in
        the badge.css file itself."""
        tmpl = env.from_string(
            "{% from 'macros/status_badge.html' import render_status_badge %}"
            "{{ render_status_badge(value='failed') }}"
        )
        out = tmpl.render()
        assert 'data-dz-tone="destructive"' in out
        # Inline Tailwind colour classes MUST NOT appear — the migration
        # moved all tone styling to components/badge.css.
        assert "hsl(var(--destructive))" not in out
        # Legacy DaisyUI class names MUST NOT appear
        assert "badge-error" not in out
        assert "badge-ghost" not in out

    # --- metric_number filter (cycle 239, UX-042 metrics-region contract) ---
    # Canonical number formatter for every metric tile across the framework.

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, "0"),
            (0, "0"),
            (5, "5"),
            (1234, "1,234"),
            (1500000, "1,500,000"),
            (-42, "-42"),
            (-12345, "-12,345"),
            (3.14159, "3.1"),  # ≥1 floats round to 1 decimal
            (1234.56, "1,234.6"),
            (0.25, "0.25"),  # sub-unit floats keep more precision
            (True, "Yes"),  # bool gets a label, not 1
            (False, "No"),
            ("£1,234", "£1,234"),  # pre-formatted strings pass through verbatim
        ],
        ids=[
            "none_zeros",
            "zero",
            "small_int",
            "thousands",
            "millions",
            "negative_int",
            "negative_thousands",
            "float_ge_one_pi",
            "float_ge_one_thousands",
            "float_sub_unit",
            "bool_true",
            "bool_false",
            "string_passthrough",
        ],
    )
    def test_metric_number(self, env, value, expected) -> None:
        """Canonical metric formatter (cycle 239, UX-042)."""
        tmpl = env.from_string("{{ val | metric_number }}")
        assert tmpl.render(val=value) == expected

    # --- timeago filter ---

    # Trivial passthrough cases — no time arithmetic involved.
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(None, ""), ("not-a-date", "not-a-date"), (12345, "12345")],
        ids=["none", "invalid_string", "non_datetime_type"],
    )
    def test_timeago_passthrough(self, env, value, expected) -> None:
        tmpl = env.from_string("{{ val|timeago }}")
        assert tmpl.render(val=value) == expected

    def test_timeago_future(self, env) -> None:
        """Future datetimes return 'just now' (no negative durations)."""
        tmpl = env.from_string("{{ val|timeago }}")
        assert tmpl.render(val=datetime.now() + timedelta(hours=1)) == "just now"

    def test_timeago_iso_string_with_z_suffix(self, env) -> None:
        """`Z` is the canonical UTC suffix in ISO 8601 — fromisoformat used
        to reject it on Python <3.11; we now normalise before parsing."""
        tmpl = env.from_string("{{ val|timeago }}")
        result = tmpl.render(val="2026-04-22T10:00:00Z")
        # Result depends on test clock; just confirm parsing succeeded
        # (passthrough would mean parse failed).
        assert result != "2026-04-22T10:00:00Z"

    def test_timeago_tz_aware_datetime_does_not_raise(self, env) -> None:
        """tz-aware values from Postgres TIMESTAMP WITH TIME ZONE columns
        used to crash with `can't subtract offset-naive and offset-aware
        datetimes` because `datetime.now()` was naive (#852)."""
        from datetime import UTC

        tmpl = env.from_string("{{ val|timeago }}")
        result = tmpl.render(val=datetime.now(tz=UTC) - timedelta(hours=2))
        assert "hour" in result

    # Plural buckets: the substring assertion confirms the right unit fires.
    @pytest.mark.parametrize(
        ("delta", "unit_substring"),
        [
            (timedelta(seconds=30), "second"),
            (timedelta(minutes=5), "minute"),
            (timedelta(hours=3), "hour"),
            (timedelta(days=15), "day"),
            (timedelta(days=60), "month"),
            (timedelta(days=400), "year"),
        ],
        ids=["seconds", "minutes", "hours", "days", "months", "years"],
    )
    def test_timeago_plural_units(self, env, delta, unit_substring) -> None:
        tmpl = env.from_string("{{ val|timeago }}")
        result = tmpl.render(val=datetime.now() - delta)
        assert unit_substring in result

    def test_timeago_date_object(self, env) -> None:
        """date (not datetime) inputs are accepted — used by audit fields."""
        tmpl = env.from_string("{{ val|timeago }}")
        result = tmpl.render(val=date.today() - timedelta(days=3))
        assert "day" in result

    def test_timeago_iso_string(self, env) -> None:
        """ISO 8601 strings parse via fromisoformat."""
        tmpl = env.from_string("{{ val|timeago }}")
        past = datetime.now() - timedelta(hours=2)
        assert "hour" in tmpl.render(val=past.isoformat())

    def test_timeago_naive_datetime_treated_as_local(self, env) -> None:
        """Naive datetimes are treated as local time (the convention every
        existing call site uses — `datetime.now() - delta`)."""
        tmpl = env.from_string("{{ val|timeago }}")
        result = tmpl.render(val=datetime.now() - timedelta(minutes=5))
        assert "minute" in result

    # Singular bucket: exact-string match pins the "1 X ago" formatter
    # (no leading "About"; no plural "s"; no "ago" elision).
    @pytest.mark.parametrize(
        ("delta", "expected"),
        [
            (timedelta(seconds=1), "1 second ago"),
            (timedelta(minutes=1), "1 minute ago"),
            (timedelta(hours=1), "1 hour ago"),
            (timedelta(days=1), "1 day ago"),
            (timedelta(days=30), "1 month ago"),
            (timedelta(days=365), "1 year ago"),
        ],
        ids=["second", "minute", "hour", "day", "month", "year"],
    )
    def test_timeago_singular_format(self, env, delta, expected) -> None:
        tmpl = env.from_string("{{ val|timeago }}")
        assert tmpl.render(val=datetime.now() - delta) == expected

    # --- slugify filter ---

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("Hello World!", "hello-world"), (None, "")],
        ids=["text", "none"],
    )
    def test_slugify(self, env, value, expected) -> None:
        tmpl = env.from_string("{{ val|slugify }}")
        assert tmpl.render(val=value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("/uploads/docs/report.pdf", "report.pdf"),
            ("https://example.com/file.txt?v=2", "file.txt"),
            ("readme.txt", "readme.txt"),
            (None, ""),
        ],
        ids=["path", "url_with_query", "plain_name", "none"],
    )
    def test_basename_or_url(self, env, value, expected) -> None:
        tmpl = env.from_string("{{ val|basename_or_url }}")
        assert tmpl.render(val=value) == expected

    # --- Jinja globals ---

    def test_dazzle_version_global(self, env) -> None:
        assert "_dazzle_version" in env.globals
        assert env.globals["_dazzle_version"]  # non-empty

    def test_use_cdn_global(self, env) -> None:
        assert "_use_cdn" in env.globals
        assert env.globals["_use_cdn"] is False


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
            if field.type and field.type.kind == FieldTypeKind.MONEY:
                # Money fields expand to _minor + _currency
                assert f"{field.name}_minor" in record, f"Missing field: {field.name}_minor"
                assert f"{field.name}_currency" in record, f"Missing field: {field.name}_currency"
            else:
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

    def test_money_field_expanded(self) -> None:
        records = generate_mock_records(_task_entity(), count=1)
        assert isinstance(records[0]["amount_minor"], int)
        assert records[0]["amount_currency"] == "GBP"


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
