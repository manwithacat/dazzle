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


def test_jinja_renderer_renders_a_minimal_view_surface() -> None:
    """Plan 8 — minimal render_surface path supports VIEW mode."""
    surface = SurfaceSpec(
        name="task_detail",
        title="Task Detail",
        mode=SurfaceMode.VIEW,
        entity_ref="Task",
    )
    ctx = {
        "fields": [
            {"key": "title", "label": "Title", "value": "Buy milk"},
            {"key": "status", "label": "Status", "value": "open"},
        ],
        "region_name": "task_detail_main",
    }
    renderer = JinjaRenderer()
    html = renderer.render(surface, ctx)
    assert isinstance(html, str)
    assert "Title" in html
    assert "Buy milk" in html
    assert "Status" in html
    assert "open" in html


def test_jinja_renderer_renders_minimal_create_form() -> None:
    """Plan 9 — render_surface emits an HTML form for CREATE mode."""
    surface = SurfaceSpec(
        name="task_create",
        title="New Task",
        mode=SurfaceMode.CREATE,
        entity_ref="Task",
    )
    ctx = {
        "fields": [
            {"name": "title", "label": "Title", "kind": "str", "required": True, "value": ""},
        ],
        "action": "/api/Task",
        "method": "POST",
        "submit_label": "Create",
    }
    html = JinjaRenderer().render(surface, ctx)
    assert isinstance(html, str)
    assert "<form" in html
    assert 'action="/api/Task"' in html
    assert 'method="POST"' in html
    assert "Title" in html
    assert "Create" in html


def test_jinja_renderer_renders_minimal_edit_form() -> None:
    """Plan 9 — render_surface emits an HTML form for EDIT mode with values."""
    surface = SurfaceSpec(
        name="task_edit",
        title="Edit Task",
        mode=SurfaceMode.EDIT,
        entity_ref="Task",
    )
    ctx = {
        "fields": [
            {
                "name": "title",
                "label": "Title",
                "kind": "str",
                "required": True,
                "value": "Buy milk",
            },
        ],
        "action": "/api/Task/42",
        "method": "POST",
        "submit_label": "Save",
    }
    html = JinjaRenderer().render(surface, ctx)
    assert "Buy milk" in html
    assert 'action="/api/Task/42"' in html
    assert "Save" in html
