"""Tests for guided multi-step form stepper (v0.29.0).

Covers:
- FormSectionContext population from surface sections
- Multi-section surfaces compile with section metadata
- Stepper template renders stage indicators
- Form template renders wizard stages with navigation
- Single-section surfaces render without stepper
"""

from __future__ import annotations

from typing import Any

from dazzle.core import ir
from dazzle.core.ir import FieldTypeKind, SurfaceMode


class _SimpleObj:
    """Simple attribute holder for template rendering tests."""

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# Template compiler: section building
# ---------------------------------------------------------------------------


class TestBuildFormSections:
    """_build_form_sections produces FormSectionContext from surface sections."""

    def test_multi_section_surface_produces_sections(self) -> None:
        from dazzle_ui.converters.template_compiler import _build_form_sections

        entity = ir.EntitySpec(
            name="Task",
            fields=[
                ir.FieldSpec(name="title", type=ir.FieldType(kind=FieldTypeKind.STR)),
                ir.FieldSpec(name="description", type=ir.FieldType(kind=FieldTypeKind.TEXT)),
                ir.FieldSpec(name="priority", type=ir.FieldType(kind=FieldTypeKind.STR)),
            ],
        )
        surface = ir.SurfaceSpec(
            name="task_form",
            mode=SurfaceMode.CREATE,
            entity_ref="Task",
            sections=[
                ir.SurfaceSection(
                    name="basics",
                    title="Basic Info",
                    elements=[
                        ir.SurfaceElement(field_name="title"),
                        ir.SurfaceElement(field_name="description"),
                    ],
                ),
                ir.SurfaceSection(
                    name="details",
                    title="Details",
                    elements=[
                        ir.SurfaceElement(field_name="priority"),
                    ],
                ),
            ],
        )
        sections = _build_form_sections(surface, entity)
        assert len(sections) == 2
        assert sections[0].name == "basics"
        assert sections[0].title == "Basic Info"
        assert len(sections[0].fields) == 2
        assert sections[0].fields[0].name == "title"
        assert sections[1].name == "details"
        assert sections[1].title == "Details"
        assert len(sections[1].fields) == 1

    def test_single_section_produces_empty(self) -> None:
        from dazzle_ui.converters.template_compiler import _build_form_sections

        surface = ir.SurfaceSpec(
            name="simple_form",
            mode=SurfaceMode.CREATE,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    title="Main",
                    elements=[ir.SurfaceElement(field_name="title")],
                ),
            ],
        )
        sections = _build_form_sections(surface, None)
        assert sections == []

    def test_no_sections_produces_empty(self) -> None:
        from dazzle_ui.converters.template_compiler import _build_form_sections

        surface = ir.SurfaceSpec(
            name="bare_form",
            mode=SurfaceMode.CREATE,
        )
        sections = _build_form_sections(surface, None)
        assert sections == []

    def test_section_title_defaults_from_name(self) -> None:
        from dazzle_ui.converters.template_compiler import _build_form_sections

        surface = ir.SurfaceSpec(
            name="form",
            mode=SurfaceMode.CREATE,
            sections=[
                ir.SurfaceSection(
                    name="basic_info",
                    elements=[ir.SurfaceElement(field_name="a")],
                ),
                ir.SurfaceSection(
                    name="review",
                    elements=[ir.SurfaceElement(field_name="b")],
                ),
            ],
        )
        sections = _build_form_sections(surface, None)
        assert sections[0].title == "Basic Info"
        assert sections[1].title == "Review"


# ---------------------------------------------------------------------------
# Form context: sections populated in compile
# ---------------------------------------------------------------------------


class TestFormSurfaceCompile:
    """_compile_form_surface populates sections for multi-section surfaces."""

    def test_create_with_sections(self) -> None:
        from dazzle_ui.converters.template_compiler import _compile_form_surface

        entity = ir.EntitySpec(
            name="Ticket",
            fields=[
                ir.FieldSpec(name="title", type=ir.FieldType(kind=FieldTypeKind.STR)),
                ir.FieldSpec(name="body", type=ir.FieldType(kind=FieldTypeKind.TEXT)),
                ir.FieldSpec(name="status", type=ir.FieldType(kind=FieldTypeKind.STR)),
            ],
        )
        surface = ir.SurfaceSpec(
            name="ticket_form",
            title="Create Ticket",
            mode=SurfaceMode.CREATE,
            entity_ref="Ticket",
            sections=[
                ir.SurfaceSection(
                    name="info",
                    title="Information",
                    elements=[
                        ir.SurfaceElement(field_name="title"),
                        ir.SurfaceElement(field_name="body"),
                    ],
                ),
                ir.SurfaceSection(
                    name="review",
                    title="Review",
                    elements=[ir.SurfaceElement(field_name="status")],
                ),
            ],
        )
        ctx = _compile_form_surface(surface, entity, "Ticket", "/api/tickets", "tickets", "/app")
        assert ctx.form is not None
        assert len(ctx.form.sections) == 2
        assert ctx.form.sections[0].name == "info"

    def test_create_without_sections(self) -> None:
        from dazzle_ui.converters.template_compiler import _compile_form_surface

        entity = ir.EntitySpec(
            name="Note",
            fields=[
                ir.FieldSpec(name="title", type=ir.FieldType(kind=FieldTypeKind.STR)),
            ],
        )
        surface = ir.SurfaceSpec(
            name="note_form",
            mode=SurfaceMode.CREATE,
            entity_ref="Note",
        )
        ctx = _compile_form_surface(surface, entity, "Note", "/api/notes", "notes", "/app")
        assert ctx.form is not None
        assert ctx.form.sections == []


# ---------------------------------------------------------------------------
# Template rendering: stepper and wizard stages
# ---------------------------------------------------------------------------


class TestFormTemplateRendering:
    """form.html renders stepper and wizard stages for multi-section forms."""

    def _make_section(self, name: str, title: str, fields: list[dict]) -> Any:
        return _SimpleObj(
            name=name,
            title=title,
            fields=[_SimpleObj(**f) for f in fields],
        )

    def _render_form(self, sections: list | None = None) -> str:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        template = env.get_template("components/form.html")

        form_obj = _SimpleObj(
            entity_name="Task",
            title="Create Task",
            fields=[
                _SimpleObj(
                    name="title",
                    label="Title",
                    type="text",
                    required=True,
                    placeholder="Title",
                    options=[],
                    source=None,
                    default=None,
                    hint=None,
                    extra={},
                )
            ],
            action_url="/api/tasks",
            method="post",
            mode="create",
            cancel_url="/tasks",
            initial_values={},
            sections=sections or [],
        )
        return template.render(form=form_obj)

    def test_no_sections_renders_flat_form(self) -> None:
        html = self._render_form()
        assert "data-dz-wizard" not in html
        assert "data-dz-stepper" not in html
        assert "data-dz-stage" not in html
        # Should still have submit button
        assert "Create" in html

    def test_sections_renders_wizard(self) -> None:
        sections = [
            self._make_section(
                "basics",
                "Basic Info",
                [
                    {
                        "name": "title",
                        "label": "Title",
                        "type": "text",
                        "required": True,
                        "placeholder": "Title",
                        "options": [],
                        "source": None,
                        "default": None,
                        "hint": None,
                        "extra": {},
                    }
                ],
            ),
            self._make_section(
                "details",
                "Details",
                [
                    {
                        "name": "priority",
                        "label": "Priority",
                        "type": "text",
                        "required": False,
                        "placeholder": "Priority",
                        "options": [],
                        "source": None,
                        "default": None,
                        "hint": None,
                        "extra": {},
                    }
                ],
            ),
        ]
        html = self._render_form(sections)
        assert "data-dz-wizard" in html
        assert "data-dz-stepper" in html
        assert 'data-dz-stage="0"' in html
        assert 'data-dz-stage="1"' in html
        assert "Basic Info" in html
        assert "Details" in html

    def test_wizard_has_navigation_buttons(self) -> None:
        sections = [
            self._make_section(
                "s1",
                "Step 1",
                [
                    {
                        "name": "a",
                        "label": "A",
                        "type": "text",
                        "required": False,
                        "placeholder": "",
                        "options": [],
                        "source": None,
                        "default": None,
                        "hint": None,
                        "extra": {},
                    }
                ],
            ),
            self._make_section(
                "s2",
                "Step 2",
                [
                    {
                        "name": "b",
                        "label": "B",
                        "type": "text",
                        "required": False,
                        "placeholder": "",
                        "options": [],
                        "source": None,
                        "default": None,
                        "hint": None,
                        "extra": {},
                    }
                ],
            ),
        ]
        html = self._render_form(sections)
        assert "data-dz-wizard-prev" in html
        assert "data-dz-wizard-next" in html
        assert "data-dz-wizard-submit" in html

    def test_second_stage_hidden_initially(self) -> None:
        sections = [
            self._make_section(
                "s1",
                "Step 1",
                [
                    {
                        "name": "a",
                        "label": "A",
                        "type": "text",
                        "required": False,
                        "placeholder": "",
                        "options": [],
                        "source": None,
                        "default": None,
                        "hint": None,
                        "extra": {},
                    }
                ],
            ),
            self._make_section(
                "s2",
                "Step 2",
                [
                    {
                        "name": "b",
                        "label": "B",
                        "type": "text",
                        "required": False,
                        "placeholder": "",
                        "options": [],
                        "source": None,
                        "default": None,
                        "hint": None,
                        "extra": {},
                    }
                ],
            ),
        ]
        html = self._render_form(sections)
        # First stage should NOT have display:none
        import re

        stage0 = re.search(r'data-dz-stage="0"[^>]*>', html)
        assert stage0 is not None
        assert "display:none" not in stage0.group(0)

        # Second stage should have display:none
        stage1 = re.search(r'data-dz-stage="1"[^>]*>', html)
        assert stage1 is not None
        assert "display:none" in stage1.group(0)

    def test_stepper_shows_step_labels(self) -> None:
        sections = [
            self._make_section(
                "s1",
                "Contact Info",
                [
                    {
                        "name": "a",
                        "label": "A",
                        "type": "text",
                        "required": False,
                        "placeholder": "",
                        "options": [],
                        "source": None,
                        "default": None,
                        "hint": None,
                        "extra": {},
                    }
                ],
            ),
            self._make_section(
                "s2",
                "Address",
                [
                    {
                        "name": "b",
                        "label": "B",
                        "type": "text",
                        "required": False,
                        "placeholder": "",
                        "options": [],
                        "source": None,
                        "default": None,
                        "hint": None,
                        "extra": {},
                    }
                ],
            ),
            self._make_section(
                "s3",
                "Review",
                [
                    {
                        "name": "c",
                        "label": "C",
                        "type": "text",
                        "required": False,
                        "placeholder": "",
                        "options": [],
                        "source": None,
                        "default": None,
                        "hint": None,
                        "extra": {},
                    }
                ],
            ),
        ]
        html = self._render_form(sections)
        assert "Contact Info" in html
        assert "Address" in html
        assert "Review" in html
        assert 'data-dz-step="0"' in html
        assert 'data-dz-step="1"' in html
        assert 'data-dz-step="2"' in html
