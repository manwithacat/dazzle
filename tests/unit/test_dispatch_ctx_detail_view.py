"""Issue #1028 (v0.66.128): regression test for the detail/VIEW
ctx-build bug.

Pre-fix, `_build_dispatch_ctx` iterated `getattr(detail, "sections", [])`
and never read `detail.fields`. `DetailContext` is a flat list, not
a sections tree — so `fields_out` was always empty and the fragment
adapter rendered EmptyState on every detail surface.

Fix: iterate `detail.fields` directly. This pins the contract."""

from __future__ import annotations

from dazzle.render.context import DetailContext, FieldContext
from dazzle.ui.runtime.page_routes import _build_dispatch_ctx


class _Surface:
    """Minimal surface stub — `_build_dispatch_ctx` reads `related_groups`
    on the surface for the detail branch."""

    related_groups: list[object] = []


class _RenderCtx:
    """Minimal render context with only the `detail` slot populated;
    the dispatch fn returns the detail branch when `detail is not None`."""

    def __init__(self, detail: DetailContext) -> None:
        self.detail = detail
        self.form = None
        self.table = None


def test_dispatch_ctx_detail_returns_fields_from_flat_fields_list() -> None:
    """The pre-fix code iterated `detail.sections` (which doesn't
    exist) and read `f.value` (also doesn't exist), yielding zero
    fields with empty values. The fix iterates `detail.fields` and
    pulls values from `detail.item` keyed by field.name — matching
    the legacy template's contract."""
    detail = DetailContext(
        entity_name="Manuscript",
        title="The Old Curiosity Shop",
        fields=[
            FieldContext(name="title", label="Title"),
            FieldContext(name="author", label="Author"),
            FieldContext(name="status", label="Status", type="badge"),
        ],
        item={
            "title": "The Old Curiosity Shop",
            "author": "Charles Dickens",
            "status": "published",
        },
    )
    ctx = _build_dispatch_ctx(_RenderCtx(detail), _Surface())
    assert ctx.get("region_name") == "Manuscript_detail"
    fields = ctx.get("fields", [])
    assert len(fields) == 3, f"expected 3 fields, got {len(fields)}: {fields!r}"
    assert fields[0]["key"] == "title"
    assert fields[0]["label"] == "Title"
    assert fields[0]["value"] == "The Old Curiosity Shop"
    assert fields[2]["kind"] == "badge"


def test_dispatch_ctx_detail_pulls_value_from_item_dict() -> None:
    """Values come from `detail.item[field.name]`, not from any
    attribute on FieldContext (which has no `value` field)."""
    detail = DetailContext(
        entity_name="Item",
        title="Item",
        fields=[FieldContext(name="qty", label="Quantity", type="number")],
        item={"qty": 42},
    )
    fields = _build_dispatch_ctx(_RenderCtx(detail), _Surface()).get("fields", [])
    assert fields[0]["value"] == 42


def test_dispatch_ctx_detail_missing_value_emits_empty_string() -> None:
    """Field declared in `detail.fields` but absent from `detail.item`
    yields empty string. None values get coerced to empty string."""
    detail = DetailContext(
        entity_name="Item",
        title="Item",
        fields=[
            FieldContext(name="missing", label="Missing"),
            FieldContext(name="explicit_none", label="None"),
        ],
        item={"explicit_none": None},
    )
    fields = _build_dispatch_ctx(_RenderCtx(detail), _Surface()).get("fields", [])
    assert fields[0]["value"] == ""
    assert fields[1]["value"] == ""


def test_dispatch_ctx_detail_falls_back_to_name_when_label_absent() -> None:
    """Label fallback chain: label → name."""
    detail = DetailContext(
        entity_name="Item",
        title="Item",
        fields=[FieldContext(name="x", label="")],
        item={"x": "v"},
    )
    fields = _build_dispatch_ctx(_RenderCtx(detail), _Surface()).get("fields", [])
    assert fields[0]["label"] == "x"


def test_dispatch_ctx_detail_empty_fields_returns_empty_list() -> None:
    """Empty fields list still produces a valid detail ctx with an
    empty fields list — the adapter then legitimately renders the
    empty state. The pre-fix bug made every detail page hit this
    path even when fields were populated."""
    detail = DetailContext(entity_name="Item", title="Item", fields=[])
    ctx = _build_dispatch_ctx(_RenderCtx(detail), _Surface())
    assert ctx.get("fields") == []
    assert ctx.get("region_name") == "Item_detail"


def test_dispatch_ctx_detail_threads_related_groups_from_surface() -> None:
    """Pre-existing related_groups thread is unchanged by the field-
    iteration fix."""

    class _RG:
        def __init__(self, name: str, title: str, display: str = "table") -> None:
            self.name = name
            self.title = title
            self.display = display

    class _SurfaceWithRG:
        related_groups = [_RG("comments", "Comments")]

    detail = DetailContext(entity_name="X", title="X", fields=[])
    ctx = _build_dispatch_ctx(_RenderCtx(detail), _SurfaceWithRG())
    rgs = ctx.get("related_groups", [])
    assert len(rgs) == 1
    assert rgs[0]["name"] == "comments"


# ── #1297: per-entity detail-viewer delegation contract ──────────────────


def test_dispatch_ctx_detail_threads_detail_context_for_delegation() -> None:
    """#1297: the VIEW dispatch ctx carries the original DetailContext
    under `detail_context` so a `render: <name>` custom detail viewer can
    delegate to the framework's generic detail rendering (the modern
    replacement for the removed Jinja `dz://components/detail_view.html`
    fall-through). It must be the *same* object, not a copy."""
    detail = DetailContext(
        entity_name="Manuscript",
        title="The Old Curiosity Shop",
        fields=[FieldContext(name="title", label="Title")],
        item={"title": "The Old Curiosity Shop"},
    )
    ctx = _build_dispatch_ctx(_RenderCtx(detail), _Surface())
    assert ctx.get("detail_context") is detail


def test_custom_detail_viewer_can_delegate_to_generic_render() -> None:
    """#1297: a custom renderer holding `ctx["detail_context"]` can call
    the exported `render_detail_view` helper to produce the standard
    detail body, then wrap/append its own chrome. This pins the full
    delegation round-trip the worked example (fixtures/custom_renderer)
    relies on."""
    from dazzle.ui.runtime import render_detail_view

    detail = DetailContext(
        entity_name="Manuscript",
        title="The Old Curiosity Shop",
        fields=[FieldContext(name="title", label="Title")],
        item={"title": "The Old Curiosity Shop"},
    )
    ctx = _build_dispatch_ctx(_RenderCtx(detail), _Surface())
    generic_html = render_detail_view(ctx["detail_context"])
    assert generic_html  # non-empty
    assert "The Old Curiosity Shop" in generic_html
    # The viewer composes bespoke chrome around the delegated body.
    composed = f'<section class="bespoke">BANNER{generic_html}</section>'
    assert generic_html in composed
