"""Cycle 240 — per-persona empty-state copy override (EX-046).

Tests the grammar extension that lets DSL authors declare persona-specific
``empty:`` copy inside ``for <persona>:`` blocks, the IR storage on
``PersonaVariant``, the compiler-side collection into
``TableContext.persona_empty_messages``, and the canonical
``fragments/empty_state.html`` rendering.

Excludes the per-request resolver in ``page_routes.py`` — that path
requires the full request/session context and is covered by integration
tests.
"""

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir import FieldModifier, FieldTypeKind, SurfaceMode

HAS_TEMPLATE_RENDERER = pytest.importorskip("dazzle_ui", reason="dazzle_ui not installed")


# ---------------------------------------------------------------------------
# Parser — `for <persona>: empty: "..."` is accepted
# ---------------------------------------------------------------------------


class TestPersonaEmptyParser:
    """Grammar extension lets DSL authors write per-persona empty copy."""

    def _parse_task_surface(self, dsl_body: str) -> ir.SurfaceSpec:
        dsl = f"""
module testapp
app testapp "Test App"

persona admin "Admin":
  description: "Full system access"

persona member "Team Member":
  description: "Regular user"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_list "Tasks":
  uses entity Task
  mode: list
  section main:
    field title "Title"
  ux:
{dsl_body}
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        return next(s for s in fragment.surfaces if s.name == "task_list")

    def test_base_empty_without_persona_variant(self) -> None:
        surface = self._parse_task_surface('    empty: "No tasks yet"\n')
        assert surface.ux is not None
        assert surface.ux.empty_message == "No tasks yet"
        assert surface.ux.persona_variants == []

    def test_empty_inside_persona_variant(self) -> None:
        """A `for <persona>: empty: "..."` block populates the variant."""
        surface = self._parse_task_surface(
            '    empty: "No tasks yet"\n'
            "    for admin:\n"
            '      empty: "No tasks yet — create one to get started"\n'
        )
        assert surface.ux is not None
        assert surface.ux.empty_message == "No tasks yet"
        assert len(surface.ux.persona_variants) == 1
        variant = surface.ux.persona_variants[0]
        assert variant.persona == "admin"
        assert variant.empty_message == "No tasks yet — create one to get started"

    def test_multiple_persona_overrides(self) -> None:
        """Multiple per-persona overrides all land on their variants."""
        surface = self._parse_task_surface(
            '    empty: "No tasks yet"\n'
            "    for admin:\n"
            '      empty: "Admin: no tasks"\n'
            "    for member:\n"
            '      empty: "You have no assigned tasks"\n'
        )
        assert surface.ux is not None
        overrides = {v.persona: v.empty_message for v in surface.ux.persona_variants}
        assert overrides == {
            "admin": "Admin: no tasks",
            "member": "You have no assigned tasks",
        }

    def test_persona_empty_coexists_with_other_variant_fields(self) -> None:
        """`empty:` inside a variant does not conflict with purpose/hide."""
        surface = self._parse_task_surface(
            '    empty: "No tasks yet"\n'
            "    for member:\n"
            '      purpose: "See your assigned tasks"\n'
            "      hide: title\n"
            '      empty: "You have no assigned tasks"\n'
        )
        variant = next(
            v for v in (surface.ux.persona_variants if surface.ux else []) if v.persona == "member"
        )
        assert variant.purpose == "See your assigned tasks"
        assert variant.hide == ["title"]
        assert variant.empty_message == "You have no assigned tasks"

    def test_no_override_leaves_variant_empty_message_none(self) -> None:
        surface = self._parse_task_surface(
            '    empty: "No tasks yet"\n    for admin:\n      purpose: "Admin view"\n'
        )
        variant = next(
            v for v in (surface.ux.persona_variants if surface.ux else []) if v.persona == "admin"
        )
        assert variant.purpose == "Admin view"
        assert variant.empty_message is None


# ---------------------------------------------------------------------------
# Compiler — persona_empty_messages dict is populated on TableContext
# ---------------------------------------------------------------------------


class TestPersonaEmptyCompilation:
    """Template compiler collects persona variants into a dict."""

    def _make_entity(self) -> ir.EntitySpec:
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
                    is_required=True,
                ),
            ],
        )

    def _make_list_surface(self, ux: ir.UXSpec | None) -> ir.SurfaceSpec:
        return ir.SurfaceSpec(
            name="task_list",
            title="Tasks",
            entity_ref="Task",
            mode=SurfaceMode.LIST,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    title="",
                    elements=[ir.SurfaceElement(field_name="title", label="Title")],
                )
            ],
            actions=[],
            ux=ux,
        )

    def test_no_variants_produces_empty_dict(self) -> None:
        from dazzle_ui.converters.template_compiler import compile_appspec_to_templates

        ux = ir.UXSpec(empty_message="No tasks yet")
        surface = self._make_list_surface(ux)
        appspec = ir.AppSpec(
            name="app",
            title="App",
            module="m",
            domain=ir.DomainSpec(entities=[self._make_entity()]),
            surfaces=[surface],
            workspaces=[],
        )
        compiled = compile_appspec_to_templates(appspec)
        page = compiled["/task"]
        assert page.table is not None
        assert page.table.empty_message == "No tasks yet"
        assert page.table.persona_empty_messages == {}

    def test_persona_variants_populate_dict(self) -> None:
        from dazzle_ui.converters.template_compiler import compile_appspec_to_templates

        ux = ir.UXSpec(
            empty_message="No tasks yet",
            persona_variants=[
                ir.PersonaVariant(persona="admin", empty_message="Admin: no tasks"),
                ir.PersonaVariant(persona="member", empty_message="You have no assigned tasks"),
            ],
        )
        surface = self._make_list_surface(ux)
        appspec = ir.AppSpec(
            name="app",
            title="App",
            module="m",
            domain=ir.DomainSpec(entities=[self._make_entity()]),
            surfaces=[surface],
            workspaces=[],
        )
        compiled = compile_appspec_to_templates(appspec)
        table = compiled["/task"].table
        assert table is not None
        # Base message unchanged
        assert table.empty_message == "No tasks yet"
        # Dict populated for both personas
        assert table.persona_empty_messages == {
            "admin": "Admin: no tasks",
            "member": "You have no assigned tasks",
        }

    def test_variant_without_empty_message_not_in_dict(self) -> None:
        from dazzle_ui.converters.template_compiler import compile_appspec_to_templates

        ux = ir.UXSpec(
            empty_message="No tasks yet",
            persona_variants=[
                ir.PersonaVariant(persona="admin", purpose="Admin view"),
                ir.PersonaVariant(persona="member", empty_message="You have no assigned tasks"),
            ],
        )
        surface = self._make_list_surface(ux)
        appspec = ir.AppSpec(
            name="app",
            title="App",
            module="m",
            domain=ir.DomainSpec(entities=[self._make_entity()]),
            surfaces=[surface],
            workspaces=[],
        )
        compiled = compile_appspec_to_templates(appspec)
        table = compiled["/task"].table
        assert table is not None
        # admin has no empty override → not in dict
        assert "admin" not in table.persona_empty_messages
        # member has override → in dict
        assert table.persona_empty_messages == {"member": "You have no assigned tasks"}


# ---------------------------------------------------------------------------
# Template — empty_state.html canonical rendering (contract gates 1-4)
# ---------------------------------------------------------------------------


class TestEmptyStateFragment:
    """Canonical full empty-state fragment: design tokens, markers, ARIA."""

    def _render(self, **ctx) -> str:
        from dazzle_ui.runtime.template_renderer import create_jinja_env

        env = create_jinja_env()
        tmpl = env.get_template("fragments/empty_state.html")
        return tmpl.render(**ctx)

    def test_renders_canonical_markers(self) -> None:
        html = self._render(empty_message="No tasks yet", entity_name="task")
        assert "dz-empty-state" in html
        assert 'role="status"' in html
        assert "No tasks yet" in html

    def test_read_only_kind_when_no_create_url(self) -> None:
        html = self._render(empty_message="No tasks yet", entity_name="task")
        assert 'data-dz-empty-kind="read-only"' in html
        # No CTA anchor
        assert "data-dz-empty-cta" not in html
        assert "Create first" not in html

    def test_actionable_kind_when_create_url_set(self) -> None:
        html = self._render(
            empty_message="No tasks yet",
            entity_name="task",
            create_url="/app/task/create",
        )
        assert 'data-dz-empty-kind="actionable"' in html
        assert "data-dz-empty-cta" in html
        assert 'href="/app/task/create"' in html
        assert "Create first task" in html

    def test_cta_uses_design_tokens_not_daisyui(self) -> None:
        html = self._render(
            empty_message="No tasks",
            entity_name="task",
            create_url="/app/task/create",
        )
        # Canonical design-token classes
        assert "bg-[hsl(var(--primary))]" in html
        assert "text-[hsl(var(--primary-foreground))]" in html
        # Legacy DaisyUI classes MUST NOT appear
        assert "btn-primary" not in html
        assert "btn-sm" not in html
        assert "text-base-content" not in html

    def test_fallback_copy_when_empty_message_missing(self) -> None:
        html = self._render(entity_name="task")
        assert "No task found." in html

    def test_default_entity_fallback(self) -> None:
        html = self._render()
        assert "No items found." in html
