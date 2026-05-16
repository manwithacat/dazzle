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
from dazzle.render.context import FieldContext, FormContext, PageContext
from dazzle.ui.runtime.template_renderer import _render_typed_body


def _create_surface() -> ir.SurfaceSpec:
    return ir.SurfaceSpec(
        name="widget_create",
        title="Create Widget",
        entity_ref="Widget",
        mode=ir.SurfaceMode.CREATE,
    )


def test_template_renderer_emits_form_tag() -> None:
    """The typed body renderer wraps fields in a <form> with FormStack markers."""
    form = FormContext(
        entity_name="Widget",
        title="Create Widget",
        fields=[FieldContext(name="title", label="Title", field_type="string")],
        action_url="/api/widgets",
        method="post",
        mode="create",
    )
    ctx = PageContext(page_title="Create Widget", layout="single_column", form=form)
    html = _render_typed_body(ctx)
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
