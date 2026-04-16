"""Cycle 245 — per-persona overrides on FormContext.

Mirrors the cycle 243 list-surface tests for the form-surface parallel
(`_apply_persona_form_overrides`). Closes gap doc #2 axis 4
(persona-unaware-affordances, create-form field visibility) for both
create and edit surfaces.
"""

import pytest

from dazzle.core import ir
from dazzle.core.ir import FieldModifier, FieldTypeKind, SurfaceMode

pytest.importorskip("dazzle_ui", reason="dazzle_ui not installed")


# ---------------------------------------------------------------------------
# Compiler — persona_hide + persona_read_only dicts on FormContext
# ---------------------------------------------------------------------------


class TestPersonaFormCompilation:
    """Compile a form surface and verify the persona dicts are populated."""

    def _make_entity(self) -> ir.EntitySpec:
        return ir.EntitySpec(
            name="Ticket",
            title="Ticket",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=FieldTypeKind.STR, max_length=200),
                    is_required=True,
                ),
                ir.FieldSpec(
                    name="description",
                    type=ir.FieldType(kind=FieldTypeKind.TEXT),
                ),
                ir.FieldSpec(
                    name="assigned_to",
                    type=ir.FieldType(kind=FieldTypeKind.STR, max_length=100),
                ),
            ],
        )

    def _make_create_surface(self, ux: ir.UXSpec | None) -> ir.SurfaceSpec:
        return ir.SurfaceSpec(
            name="ticket_create",
            title="Create Ticket",
            entity_ref="Ticket",
            mode=SurfaceMode.CREATE,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    title="",
                    elements=[
                        ir.SurfaceElement(field_name="title", label="Title"),
                        ir.SurfaceElement(field_name="description", label="Description"),
                        ir.SurfaceElement(field_name="assigned_to", label="Assigned To"),
                    ],
                )
            ],
            actions=[],
            ux=ux,
        )

    def _compile_form(self, ux: ir.UXSpec | None):
        from dazzle_ui.converters.template_compiler import compile_appspec_to_templates

        appspec = ir.AppSpec(
            name="app",
            title="App",
            module="m",
            domain=ir.DomainSpec(entities=[self._make_entity()]),
            surfaces=[self._make_create_surface(ux)],
            workspaces=[],
        )
        return compile_appspec_to_templates(appspec)["/ticket/create"]

    def test_no_variants_produces_empty_dicts(self) -> None:
        page = self._compile_form(ir.UXSpec())
        assert page.form is not None
        assert page.form.persona_hide == {}
        assert page.form.persona_read_only == set()

    def test_persona_hide_populates_dict(self) -> None:
        ux = ir.UXSpec(
            persona_variants=[
                ir.PersonaVariant(persona="customer", hide=["assigned_to"]),
            ],
        )
        page = self._compile_form(ux)
        form = page.form
        assert form is not None
        assert form.persona_hide == {"customer": ["assigned_to"]}

    def test_persona_read_only_populates_set(self) -> None:
        ux = ir.UXSpec(
            persona_variants=[
                ir.PersonaVariant(persona="viewer", read_only=True),
            ],
        )
        page = self._compile_form(ux)
        form = page.form
        assert form is not None
        assert form.persona_read_only == {"viewer"}

    def test_multiple_personas_and_fields(self) -> None:
        ux = ir.UXSpec(
            persona_variants=[
                ir.PersonaVariant(
                    persona="customer",
                    hide=["assigned_to", "description"],
                ),
                ir.PersonaVariant(persona="viewer", read_only=True),
                ir.PersonaVariant(persona="admin"),  # no overrides
            ],
        )
        page = self._compile_form(ux)
        form = page.form
        assert form is not None
        assert form.persona_hide == {"customer": ["assigned_to", "description"]}
        assert form.persona_read_only == {"viewer"}


# ---------------------------------------------------------------------------
# Resolver helper — _apply_persona_form_overrides
# ---------------------------------------------------------------------------


class TestApplyPersonaFormOverrides:
    """Exercise the form resolver helper directly."""

    def _make_form(
        self,
        field_names: list[str] | None = None,
        persona_hide: dict[str, list[str]] | None = None,
        persona_read_only: set[str] | None = None,
        initial_values: dict | None = None,
        with_sections: bool = False,
    ):
        from dazzle_ui.runtime.template_context import (
            FieldContext,
            FormContext,
            FormSectionContext,
        )

        field_names = field_names or ["title", "description", "assigned_to"]
        fields = [FieldContext(name=name, label=name.title()) for name in field_names]
        sections = []
        if with_sections:
            sections = [
                FormSectionContext(
                    name="main",
                    title="Main",
                    fields=[FieldContext(name=n, label=n.title()) for n in field_names],
                )
            ]
        return FormContext(
            entity_name="Ticket",
            title="Create Ticket",
            fields=fields,
            action_url="/tickets",
            mode="create",
            sections=sections,
            initial_values=initial_values or {},
            persona_hide=persona_hide or {},
            persona_read_only=persona_read_only or set(),
        )

    def test_no_roles_is_noop(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_form_overrides

        form = self._make_form(persona_hide={"customer": ["assigned_to"]})
        aborted = _apply_persona_form_overrides(form, [])
        assert aborted is False
        assert {f.name for f in form.fields} == {"title", "description", "assigned_to"}

    def test_hide_removes_matching_fields(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_form_overrides

        form = self._make_form(persona_hide={"customer": ["assigned_to"]})
        aborted = _apply_persona_form_overrides(form, ["customer"])
        assert aborted is False
        assert {f.name for f in form.fields} == {"title", "description"}

    def test_hide_also_strips_initial_values(self) -> None:
        """Hidden fields must not leak through pre-filled initial values."""
        from dazzle_ui.runtime.page_routes import _apply_persona_form_overrides

        form = self._make_form(
            persona_hide={"customer": ["assigned_to"]},
            initial_values={"title": "x", "assigned_to": "leak@example.com"},
        )
        _apply_persona_form_overrides(form, ["customer"])
        assert "assigned_to" not in form.initial_values
        assert form.initial_values == {"title": "x"}

    def test_hide_also_strips_sections(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_form_overrides

        form = self._make_form(
            persona_hide={"customer": ["assigned_to"]},
            with_sections=True,
        )
        _apply_persona_form_overrides(form, ["customer"])
        for section in form.sections:
            assert "assigned_to" not in {f.name for f in section.fields}

    def test_role_prefix_stripped(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_form_overrides

        form = self._make_form(persona_hide={"customer": ["assigned_to"]})
        _apply_persona_form_overrides(form, ["role_customer"])
        assert "assigned_to" not in {f.name for f in form.fields}

    def test_non_matching_role_is_noop(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_form_overrides

        form = self._make_form(persona_hide={"customer": ["assigned_to"]})
        _apply_persona_form_overrides(form, ["admin"])
        # All fields preserved
        assert {f.name for f in form.fields} == {"title", "description", "assigned_to"}

    def test_read_only_returns_abort_signal(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_form_overrides

        form = self._make_form(persona_read_only={"viewer"})
        aborted = _apply_persona_form_overrides(form, ["viewer"])
        assert aborted is True
        # Fields NOT mutated — caller decides what to do
        assert {f.name for f in form.fields} == {"title", "description", "assigned_to"}

    def test_read_only_takes_precedence_over_hide(self) -> None:
        """A persona that is both hide-listed and read-only aborts first."""
        from dazzle_ui.runtime.page_routes import _apply_persona_form_overrides

        form = self._make_form(
            persona_hide={"viewer": ["assigned_to"]},
            persona_read_only={"viewer"},
        )
        aborted = _apply_persona_form_overrides(form, ["viewer"])
        assert aborted is True

    def test_first_matching_role_wins(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_form_overrides

        form = self._make_form(
            persona_hide={
                "customer": ["assigned_to"],
                "agent": ["description"],
            }
        )
        # customer matches first, agent's override is ignored
        _apply_persona_form_overrides(form, ["customer", "agent"])
        field_names = {f.name for f in form.fields}
        assert "assigned_to" not in field_names
        assert "description" in field_names

    def test_empty_hide_list_is_noop(self) -> None:
        from dazzle_ui.runtime.page_routes import _apply_persona_form_overrides

        form = self._make_form(persona_hide={"customer": []})
        _apply_persona_form_overrides(form, ["customer"])
        assert {f.name for f in form.fields} == {"title", "description", "assigned_to"}
