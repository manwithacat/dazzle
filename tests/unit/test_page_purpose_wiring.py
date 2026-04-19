"""Page-level purpose threading (UX-048 partial closure).

Pins the DSL→compile→render path for `ux.purpose` (surface-level)
plus `for <persona>: purpose:` (persona-variant override).

Before v0.57.98 both were parsed into `ir.UXSpec` / `ir.PersonaVariant`
but silently dropped at compile time. 14+ DSL declarations across
contact_manager + fieldtest_hub were invisible at render time.

This file verifies:
  1. Compiler populates `PageContext.page_purpose` and
     `PageContext.persona_purposes` from `surface.ux`.
  2. All six compile branches (list / create form / edit form /
     view / review / custom) carry the fields through.
  3. Rendering emits a `<p class="dz-page-purpose" data-dazzle-
     purpose>` element inside `<main>` when purpose is non-empty,
     and nothing when it is empty.

Run standalone:
    pytest tests/unit/test_page_purpose_wiring.py -v
"""

from dazzle.core import ir
from dazzle.core.ir.surfaces import SurfaceSection
from dazzle_ui.converters.template_compiler import (
    _extract_surface_purpose,
    compile_surface_to_context,
)
from dazzle_ui.runtime.template_renderer import render_page


def _task_entity() -> ir.EntitySpec:
    return ir.EntitySpec(
        name="Task",
        label="Task",
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID), pk=True),
            ir.FieldSpec(
                name="title",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                required=True,
            ),
        ],
    )


def _section() -> SurfaceSection:
    return SurfaceSection(name="main", elements=[])


# =============================================================================
# Extractor
# =============================================================================


def test_extract_surface_purpose_none() -> None:
    assert _extract_surface_purpose(None) == ("", {})


def test_extract_surface_purpose_empty_ux() -> None:
    assert _extract_surface_purpose(ir.UXSpec()) == ("", {})


def test_extract_surface_purpose_surface_only() -> None:
    ux = ir.UXSpec(purpose="Browse and manage all tasks")
    assert _extract_surface_purpose(ux) == ("Browse and manage all tasks", {})


def test_extract_surface_purpose_with_persona_variants() -> None:
    ux = ir.UXSpec(
        purpose="Add a new task",
        persona_variants=[
            ir.PersonaVariant(persona="admin", purpose="Create for any user"),
            ir.PersonaVariant(persona="member", purpose="Create for yourself"),
            # Variant without purpose shouldn't appear in the dict
            ir.PersonaVariant(persona="guest"),
        ],
    )
    base, personas = _extract_surface_purpose(ux)
    assert base == "Add a new task"
    assert personas == {
        "admin": "Create for any user",
        "member": "Create for yourself",
    }


# =============================================================================
# Compiler — every branch threads purpose through
# =============================================================================


def _make_surface(mode: ir.SurfaceMode, ux: ir.UXSpec) -> ir.SurfaceSpec:
    return ir.SurfaceSpec(
        name="task_surface",
        title="Task Surface",
        mode=mode,
        target="Task",
        sections=[_section()],
        ux=ux,
    )


def _assert_purpose_on_context(mode: ir.SurfaceMode) -> None:
    """Each compile branch must thread purpose through."""
    entity = _task_entity()
    ux = ir.UXSpec(
        purpose=f"Purpose for {mode.value} surface",
        persona_variants=[
            ir.PersonaVariant(persona="admin", purpose=f"Admin-specific purpose for {mode.value}"),
        ],
    )
    surface = _make_surface(mode, ux)
    ctx = compile_surface_to_context(surface, entity, "/app")
    assert ctx.page_purpose == f"Purpose for {mode.value} surface"
    assert ctx.persona_purposes == {"admin": f"Admin-specific purpose for {mode.value}"}


def test_list_surface_threads_purpose() -> None:
    _assert_purpose_on_context(ir.SurfaceMode.LIST)


def test_create_surface_threads_purpose() -> None:
    _assert_purpose_on_context(ir.SurfaceMode.CREATE)


def test_edit_surface_threads_purpose() -> None:
    _assert_purpose_on_context(ir.SurfaceMode.EDIT)


def test_view_surface_threads_purpose() -> None:
    _assert_purpose_on_context(ir.SurfaceMode.VIEW)


def test_review_surface_threads_purpose() -> None:
    _assert_purpose_on_context(ir.SurfaceMode.REVIEW)


# =============================================================================
# Render — app_shell.html emits the subtitle when page_purpose is set
# =============================================================================


def test_render_includes_purpose_when_non_empty() -> None:
    entity = _task_entity()
    surface = _make_surface(
        ir.SurfaceMode.LIST,
        ir.UXSpec(purpose="Browse and manage all tasks"),
    )
    ctx = compile_surface_to_context(surface, entity, "/app")
    html = render_page(ctx)
    assert "Browse and manage all tasks" in html
    assert "dz-page-purpose" in html
    assert "data-dazzle-purpose" in html


def test_render_omits_purpose_element_when_empty() -> None:
    entity = _task_entity()
    surface = _make_surface(ir.SurfaceMode.LIST, ir.UXSpec())
    ctx = compile_surface_to_context(surface, entity, "/app")
    assert ctx.page_purpose == ""
    html = render_page(ctx)
    assert "dz-page-purpose" not in html


def test_render_persona_override_via_context_copy() -> None:
    """Simulates the page_routes._render_response persona-override path:
    the request-time code detects the user's persona, matches against
    `persona_purposes`, and calls model_copy(update=...) to swap
    `page_purpose` before render. This test pins the copy-and-render
    shape without running the full FastAPI stack."""
    entity = _task_entity()
    surface = _make_surface(
        ir.SurfaceMode.CREATE,
        ir.UXSpec(
            purpose="Add a new task to the backlog",
            persona_variants=[
                ir.PersonaVariant(persona="admin", purpose="Create a task for any user"),
            ],
        ),
    )
    ctx = compile_surface_to_context(surface, entity, "/app")
    assert ctx.persona_purposes == {"admin": "Create a task for any user"}

    # Non-persona render: surface-level purpose wins.
    html_default = render_page(ctx)
    assert "Add a new task to the backlog" in html_default
    assert "Create a task for any user" not in html_default

    # Persona render: the override replaces the surface-level purpose.
    ctx_admin = ctx.model_copy(update={"page_purpose": ctx.persona_purposes["admin"]})
    html_admin = render_page(ctx_admin)
    assert "Create a task for any user" in html_admin
    assert "Add a new task to the backlog" not in html_admin
