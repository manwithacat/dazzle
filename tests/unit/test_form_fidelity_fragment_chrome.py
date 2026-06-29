"""Regression test for #1103 — fidelity scorer + Fragment FormStack.

Two-pronged fix:

1. ``template_renderer._render_typed_body`` wraps form fields in a real
   ``<form class="dz-form-stack" hx-post=… data-dazzle-form=…>`` so the
   scorer sees the same structural markers a runtime user does.

2. ``fidelity_scorer._check_form_structure`` also accepts a ``div``/
   ``dz-region`` carrying ``data-dazzle-form`` or class
   ``dz-form-stack`` as satisfying the "has a form" assertion — defence
   in depth in case a future renderer wraps fields in a custom element.
"""

from dazzle.core import ir
from dazzle.core.fidelity_scorer import _check_form_structure, parse_html
from dazzle.page.runtime.template_renderer import _render_typed_body
from dazzle.render.context import FieldContext, FormContext, PageContext


def _create_surface() -> ir.SurfaceSpec:
    return ir.SurfaceSpec(
        name="widget_create",
        title="Create Widget",
        entity_ref="Widget",
        mode=ir.SurfaceMode.CREATE,
    )


def _edit_surface() -> ir.SurfaceSpec:
    return ir.SurfaceSpec(
        name="widget_edit",
        title="Edit Widget",
        entity_ref="Widget",
        mode=ir.SurfaceMode.EDIT,
    )


def _render_substrate_form(form: FormContext, surface: ir.SurfaceSpec) -> str:
    """Render a form through the substrate dispatch path (the default since
    ADR-0049 Phase 3b) — the same FieldContext→dispatch-ctx→FormStack path a
    real request takes, minus the http boot."""
    from types import SimpleNamespace

    from dazzle.http.runtime.page_routes import _build_dispatch_ctx
    from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
    from dazzle.render.fragment import FragmentRenderer

    render_ctx = SimpleNamespace(form=form, table=None, detail=None)
    ctx = _build_dispatch_ctx(render_ctx, surface, services=None)
    return FragmentRenderer().render(
        FragmentSurfaceAdapter()._build_form(surface, ctx, mode=surface.mode)
    )


def test_legacy_form_path_raises_loudly() -> None:
    """ADR-0049 Phase 3b (D4): forms render via the substrate now — reaching
    the legacy `_render_typed_body` with a form ctx (no RuntimeServices) is a
    misconfiguration that fails loudly, never a blank page."""
    import pytest

    form = FormContext(
        entity_name="Widget",
        title="Create Widget",
        fields=[FieldContext(name="title", label="Title", field_type="string")],
        action_url="/api/widgets",
        method="post",
        mode="create",
    )
    ctx = PageContext(page_title="Create Widget", layout="single_column", form=form)
    with pytest.raises(RuntimeError, match="typed substrate"):
        _render_typed_body(ctx)


def test_substrate_emits_form_tag() -> None:
    """The substrate form path wraps fields in a <form> with the FormStack
    contract markers the fidelity scorer + RBAC checker key off."""
    form = FormContext(
        entity_name="Widget",
        title="Create Widget",
        fields=[FieldContext(name="title", label="Title", field_type="string")],
        action_url="/api/widgets",
        method="post",
        mode="create",
    )
    html = _render_substrate_form(form, _create_surface())
    assert "<form " in html
    assert 'class="dz-form-stack"' in html
    assert 'hx-post="/api/widgets"' in html
    assert 'data-dazzle-form="Widget"' in html
    assert 'data-dazzle-form-mode="create"' in html


def test_scorer_accepts_form_tag_with_formstack_markers() -> None:
    """A literal <form class=dz-form-stack hx-post=…> satisfies the structural probe."""
    html = (
        '<form class="dz-form-stack" hx-post="/api/widgets" '
        'data-dazzle-form="Widget" data-dazzle-form-mode="create">'
        '<input name="title"/></form>'
    )
    gaps = _check_form_structure(_create_surface(), None, parse_html(html))
    form_gaps = [g for g in gaps if g.target == "form"]
    assert form_gaps == []


def test_scorer_accepts_fragment_div_with_data_dazzle_form() -> None:
    """A bare div carrying data-dazzle-form (no literal <form> tag) still counts."""
    html = (
        '<dz-region class="dz-region--kind-form">'
        '<div data-dazzle-form="Widget" hx-post="/api/widgets">'
        '<input name="title"/></div></dz-region>'
    )
    gaps = _check_form_structure(_create_surface(), None, parse_html(html))
    form_gaps = [g for g in gaps if g.target == "form"]
    assert form_gaps == []


def test_scorer_still_fires_on_bare_fields() -> None:
    """Pure inputs with no form marker at all still produce a 'missing form' gap."""
    html = '<label>x</label><input name="title"/>'
    gaps = _check_form_structure(_create_surface(), None, parse_html(html))
    form_gaps = [g for g in gaps if g.target == "form"]
    assert len(form_gaps) == 1
    assert form_gaps[0].recommendation == "Add a <form> element."


# --- #1291: the default (non-Fragment) render path must emit a submit button ---
#
# Before #1291 the legacy path wrapped fields in a <form> but emitted no
# <button type="submit">, so any create/edit surface without `render: fragment`
# rendered an unsubmittable form. These tests pin a cross-path invariant: every
# form _render_typed_body produces carries exactly one submit button, matching
# the Fragment path's canonical `dz-submit` markup and label convention
# ("Create" on create, "Save" on edit).


def _submit_buttons(html: str) -> list[str]:
    """Return the inner text of every <button type="submit"> in *html*."""
    import re

    return re.findall(r'<button type="submit"[^>]*>(.*?)</button>', html, flags=re.DOTALL)


def test_default_path_create_form_has_submit_button() -> None:
    """A create FormContext renders exactly one submit button labelled 'Create'."""
    form = FormContext(
        entity_name="Widget",
        title="Create Widget",
        fields=[FieldContext(name="title", label="Title", field_type="string")],
        action_url="/api/widgets",
        method="post",
        mode="create",
    )
    html = _render_substrate_form(form, _create_surface())
    assert 'type="submit"' in html
    assert 'class="dz-submit dz-submit--variant-primary"' in html
    assert _submit_buttons(html) == ["Create"]


def test_default_path_edit_form_has_submit_button() -> None:
    """An edit FormContext renders exactly one submit button labelled 'Save'."""
    form = FormContext(
        entity_name="Widget",
        title="Edit Widget",
        fields=[FieldContext(name="title", label="Title", field_type="string")],
        action_url="/api/widgets/123",
        method="put",
        mode="edit",
    )
    html = _render_substrate_form(form, _edit_surface())
    assert _submit_buttons(html) == ["Save"]
    # Edit forms post via hx-put; the submit lives inside the <form>.
    assert html.index('type="submit"') > html.index("<form ")
    assert 'hx-put="/api/widgets/123"' in html
