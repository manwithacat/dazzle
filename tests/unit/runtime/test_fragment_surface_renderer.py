"""FragmentSurfaceRenderer adapter — uniform (surface, ctx) interface."""

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.http.runtime.renderers.fragment import FragmentSurfaceRenderer


def test_fragment_surface_renderer_renders_a_minimal_list_surface() -> None:
    """The adapter accepts a SurfaceSpec + ctx dict and returns HTML
    containing the row content. Internally it builds a Fragment tree
    via FragmentSurfaceAdapter and renders via FragmentRenderer."""
    surface = SurfaceSpec(
        name="task_list",
        title="Task List",
        mode=SurfaceMode.LIST,
        entity_ref="Task",
    )
    ctx = {
        "items": [{"id": "1", "title": "Buy milk"}, {"id": "2", "title": "Walk dog"}],
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "region_name": "task_list_main",
        "endpoint": "/api/test",
        "total": 2,
    }
    renderer = FragmentSurfaceRenderer()
    html = renderer.render(surface, ctx)
    assert isinstance(html, str)
    # Canonical (ADR-0049 Task 4e): rows hydrate from /api, so the first paint
    # is a skeleton table (column header + chrome), not inline row content.
    assert "Title" in html  # column header
    assert "<table" in html
    assert 'class="dz-table-body"' in html  # the hydrating skeleton tbody
    assert 'hx-get="/api/test' in html  # points at the row-data endpoint
    assert "dz-surface" in html  # uses Fragment chrome, not Jinja chrome
    assert "Buy milk" not in html  # row content is NOT inlined


def test_fragment_surface_renderer_signature_is_stable() -> None:
    """The (surface, ctx) -> str signature is the dispatcher contract.

    Pre-#1051 this test compared FragmentSurfaceRenderer against the
    JinjaRenderer adapter; the adapter was retired so the gate now
    just pins the FragmentSurfaceRenderer signature directly.
    """
    fragment_render = FragmentSurfaceRenderer.render

    # render(self, surface, ctx) — 3 positional parameters
    assert fragment_render.__code__.co_argcount == 3
    assert fragment_render.__code__.co_varnames[:3] == ("self", "surface", "ctx")
