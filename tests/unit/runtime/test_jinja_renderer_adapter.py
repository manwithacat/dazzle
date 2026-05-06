"""JinjaRenderer adapter: same HTML as the legacy direct path.

Plan 3 Task 1 — the registry-facing JinjaRenderer is a thin wrapper around
``dazzle_ui.runtime.template_renderer.render_surface``. The adapter contract
is ``(surface, ctx) -> str``; the helper turns the SurfaceSpec + flat ctx
dict into a minimal ``PageContext`` and delegates to the existing
``render_page`` machinery.
"""

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle_back.runtime.renderers.jinja import JinjaRenderer


def test_jinja_renderer_renders_a_minimal_list_surface() -> None:
    surface = SurfaceSpec(
        name="task_list",
        title="Task List",
        mode=SurfaceMode.LIST,
        entity_ref="Task",
    )
    ctx = {
        "items": [
            {"id": "1", "title": "Buy milk"},
            {"id": "2", "title": "Walk dog"},
        ],
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "endpoint": "/api/test",
        "region_name": "task_list_main",
        "total": 2,
    }
    renderer = JinjaRenderer()
    html = renderer.render(surface, ctx)
    assert isinstance(html, str)
    assert "Task List" in html or "task_list" in html
    assert "Buy milk" in html
    assert "Walk dog" in html
    assert "<table" in html
