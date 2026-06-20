"""Issue #1031 (v0.66.131): regression test for multi-section form
rendering through the typed-Fragment adapter.

Pre-fix, `_build_dispatch_ctx` only read `form.fields` (the
flattened list) and never inspected `form.sections`. The adapter
wrapped everything in one `FormStack` with no group headings.
Multi-section forms (cyfuture has 42 of them, including
`company_create` with `lookup`/`details` sections) rendered as a
flat list with no visual grouping.

Fix: thread `form.sections` into the dispatch ctx; adapter wraps
each section's fields in a `FormSection` primitive INSIDE the outer
`FormStack` so the result is one `<form>` element with N `<section
class="dz-form-section">` groupings."""

from __future__ import annotations

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.render.context import (
    FieldContext,
    FormContext,
    FormSectionContext,
)
from dazzle.render.fragment import FormSection, FormStack, FragmentRenderer


class _Surface:
    name = "company_create"
    title = "Add Company"
    related_groups: list = []


class _RC:
    def __init__(self, form: FormContext) -> None:
        self.form = form
        self.detail = None
        self.table = None


def _two_section_form() -> FormContext:
    return FormContext(
        entity_name="Company",
        title="Add Company",
        action_url="/companies",
        method="POST",
        mode="create",
        fields=[
            FieldContext(name="company_number", label="Company Number"),
            FieldContext(name="company_name", label="Company Name"),
            FieldContext(name="trading_status", label="Trading Status"),
        ],
        sections=[
            FormSectionContext(
                name="lookup",
                title="Find Company",
                fields=[FieldContext(name="company_number", label="Company Number")],
            ),
            FormSectionContext(
                name="details",
                title="Company Details",
                fields=[
                    FieldContext(name="company_name", label="Company Name"),
                    FieldContext(name="trading_status", label="Trading Status"),
                ],
            ),
        ],
    )


def test_dispatch_ctx_threads_form_sections() -> None:
    """`_build_dispatch_ctx` returns a `sections` key with each
    section's fields keyed by name (matched against the flat
    `fields_out` index)."""
    ctx = _build_dispatch_ctx(_RC(_two_section_form()), _Surface())
    sections = ctx.get("sections", [])
    assert len(sections) == 2
    assert sections[0]["name"] == "lookup"
    assert sections[0]["title"] == "Find Company"
    assert [f["name"] for f in sections[0]["fields"]] == ["company_number"]
    assert sections[1]["name"] == "details"
    assert [f["name"] for f in sections[1]["fields"]] == [
        "company_name",
        "trading_status",
    ]


def test_dispatch_ctx_omits_sections_for_single_section_form() -> None:
    """Single-section forms (or zero sections) shouldn't grow a
    redundant heading. The dispatch ctx omits `sections` entirely
    so the adapter falls back to the flat FormStack path."""
    form = FormContext(
        entity_name="X",
        title="X",
        action_url="/x",
        method="POST",
        mode="create",
        fields=[FieldContext(name="t", label="T")],
        sections=[
            FormSectionContext(
                name="main",
                title="Main",
                fields=[FieldContext(name="t", label="T")],
            ),
        ],
    )
    ctx = _build_dispatch_ctx(_RC(form), _Surface())
    assert "sections" not in ctx


def test_form_adapter_emits_dz_form_section_per_section() -> None:
    """The adapter wraps each ctx section in a FormSection inside the
    outer FormStack. Renderer emits `<section class="dz-form-section">`
    + `<h3 class="dz-form-section-title">` per section."""
    ctx = _build_dispatch_ctx(_RC(_two_section_form()), _Surface())
    adapter = FragmentSurfaceAdapter()
    result = adapter._build_form(_Surface(), ctx, mode=SurfaceMode.CREATE)
    html = FragmentRenderer().render(result)
    assert html.count('class="dz-form-section"') == 2
    assert html.count('class="dz-form-section-title"') == 2
    assert ">Find Company</h3>" in html
    assert ">Company Details</h3>" in html


def test_form_adapter_emits_single_form_element_around_all_sections() -> None:
    """All sections live INSIDE one `<form>` — a single Submit at
    the bottom commits all fields together. Multiple `<form>` tags
    would mean multiple submission targets, breaking the contract."""
    ctx = _build_dispatch_ctx(_RC(_two_section_form()), _Surface())
    adapter = FragmentSurfaceAdapter()
    result = adapter._build_form(_Surface(), ctx, mode=SurfaceMode.CREATE)
    html = FragmentRenderer().render(result)
    assert html.count("<form") == 1
    assert html.count('type="submit"') == 1


def test_form_section_with_note_emits_paragraph() -> None:
    """`section.note` from FormSectionContext threads through to the
    primitive's `note` field and renders as
    `<p class="dz-form-section-note">…</p>`."""
    form = FormContext(
        entity_name="X",
        title="X",
        action_url="/x",
        method="POST",
        mode="create",
        fields=[FieldContext(name="a", label="A"), FieldContext(name="b", label="B")],
        sections=[
            FormSectionContext(
                name="s1",
                title="One",
                fields=[FieldContext(name="a", label="A")],
                note="Required for compliance",
            ),
            FormSectionContext(
                name="s2",
                title="Two",
                fields=[FieldContext(name="b", label="B")],
            ),
        ],
    )
    ctx = _build_dispatch_ctx(_RC(form), _Surface())
    adapter = FragmentSurfaceAdapter()
    result = adapter._build_form(_Surface(), ctx, mode=SurfaceMode.CREATE)
    html = FragmentRenderer().render(result)
    assert '<p class="dz-form-section-note">Required for compliance</p>' in html
    # Section without note doesn't emit an empty <p>.
    assert html.count('class="dz-form-section-note"') == 1


def test_form_section_primitive_validates_non_empty_fields() -> None:
    """FormSection requires at least one field — empty section is a
    construction error, not a silent zero-field render."""
    import pytest

    with pytest.raises(ValueError, match="at least one field"):
        FormSection(title="Empty", fields=())


def test_form_stack_with_form_section_children_renders_via_renderer() -> None:
    """End-to-end: build FormStack carrying FormSection items
    directly (no adapter), render via FragmentRenderer."""
    from dazzle.render.fragment import URL, Field, Submit

    fs = FormStack(
        action=URL("/x"),
        fields=(
            FormSection(
                title="A",
                fields=(Field(name="x", label="X"),),
            ),
            FormSection(
                title="B",
                fields=(Field(name="y", label="Y"),),
            ),
        ),
        method="POST",
        submit=Submit(label="Save"),
    )
    html = FragmentRenderer().render(fs)
    assert html.count('class="dz-form-section"') == 2
    assert html.count("<form") == 1
