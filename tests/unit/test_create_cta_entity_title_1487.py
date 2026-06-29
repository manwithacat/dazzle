"""#1487 — the list-view create CTA reads the entity's declared display title,
not the raw PascalCase identifier ("New Curriculum Plan", not "New CurriculumPlan").

Covers both render paths (the typed-Fragment `CreateButton` and the legacy
`table_renderer.render_filterable_table`) plus the compiler seam that threads the
title onto `TableContext.entity_title`.
"""

from dazzle.core import ir
from dazzle.core.ir import FieldModifier, FieldTypeKind, SurfaceMode
from dazzle.page.converters.template_compiler import compile_surface_to_context
from dazzle.render.fragment import CreateButton, FragmentRenderer


def _entity(title: str | None) -> ir.EntitySpec:
    return ir.EntitySpec(
        name="CurriculumPlan",
        title=title,
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
        ],
    )


def _list_surface() -> ir.SurfaceSpec:
    return ir.SurfaceSpec(
        name="curriculumplan_list",
        title="Curriculum Plans",  # the LIST title — distinct from the entity title
        entity_ref="CurriculumPlan",
        mode=SurfaceMode.LIST,
        sections=[
            ir.SurfaceSection(
                name="main",
                title="Main",
                elements=[ir.SurfaceElement(field_name="name", label="Name")],
            )
        ],
        actions=[],
        ux=None,
    )


# ── Compiler seam ────────────────────────────────────────────────────────


def test_compiler_threads_entity_title_onto_table_context() -> None:
    ctx = compile_surface_to_context(_list_surface(), _entity("Curriculum Plan"))
    assert ctx.table is not None
    assert ctx.table.entity_title == "Curriculum Plan"
    # distinct from the list/surface title
    assert ctx.table.title != ctx.table.entity_title


def test_compiler_entity_title_empty_when_no_declared_title() -> None:
    ctx = compile_surface_to_context(_list_surface(), _entity(None))
    assert ctx.table is not None
    assert ctx.table.entity_title == ""


# ── Fragment render path (typed CreateButton) ────────────────────────────


def test_fragment_create_button_uses_declared_title() -> None:
    html = FragmentRenderer().render(
        CreateButton(
            href="/app/curriculumplan/create",
            entity_name="CurriculumPlan",
            entity_title="Curriculum Plan",
        )
    )
    assert "New Curriculum Plan" in html
    assert "New CurriculumPlan<" not in html  # the bug: raw PascalCase id
    # the RBAC contract anchor still uses the raw entity name
    assert 'data-dazzle-action="CurriculumPlan.create"' in html


def test_fragment_create_button_falls_back_to_humanised_name() -> None:
    html = FragmentRenderer().render(CreateButton(href="/x", entity_name="CurriculumPlan"))
    assert "New CurriculumPlan" in html


def test_fragment_explicit_label_override_still_wins() -> None:
    html = FragmentRenderer().render(
        CreateButton(
            href="/x",
            entity_name="CurriculumPlan",
            entity_title="Curriculum Plan",
            label="Add a plan",
        )
    )
    assert "Add a plan" in html
    assert "New Curriculum Plan" not in html


# ADR-0049 Task 6: the legacy `table_renderer` create-CTA + search-placeholder
# tests are removed with the deleted module. The same #1487 behaviour (declared
# title in the create CTA + search placeholder) is covered on the substrate path
# by `test_fragment_create_button_uses_declared_title` +
# `test_fragment_search_placeholder_uses_declared_title` above.


def test_fragment_search_placeholder_uses_declared_title() -> None:
    from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter

    toolbar = FragmentSurfaceAdapter()._build_list_toolbar(
        search_enabled=True,
        search_fields=["name"],
        filter_values={},
        columns=[],
        entity_name="CurriculumPlan",
        entity_title="Curriculum Plan",
        endpoint="/api/curriculumplan",
        region_name="curriculumplan",
    )
    html = "".join(FragmentRenderer().render(f) for f in toolbar)
    assert 'placeholder="Search curriculum plan' in html
    # the FTS endpoint legitimately carries the raw entity name; the VISIBLE
    # placeholder must not.
    assert 'placeholder="Search CurriculumPlan' not in html


def test_fragment_search_placeholder_default_when_no_title() -> None:
    from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter

    toolbar = FragmentSurfaceAdapter()._build_list_toolbar(
        search_enabled=True,
        search_fields=["name"],
        filter_values={},
        columns=[],
        entity_name="CurriculumPlan",
        entity_title="",
        endpoint="/api/curriculumplan",
        region_name="curriculumplan",
    )
    html = "".join(FragmentRenderer().render(f) for f in toolbar)
    assert 'placeholder="Search…"' in html
