"""Phase-5 parity test: simple_task.task_list renders via Fragment with
the same observable behaviour as the Jinja path."""

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle_back.runtime.renderers.dispatch import dispatch_render
from dazzle_back.runtime.renderers.init import register_default_renderers
from dazzle_back.runtime.services import RuntimeServices


def _make_services() -> RuntimeServices:
    services = RuntimeServices()
    register_default_renderers(services)
    return services


def _ctx() -> dict:
    """Deterministic task-list context."""
    return {
        "items": [
            {"id": "1", "title": "Buy milk"},
            {"id": "2", "title": "Walk dog"},
        ],
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "region_name": "task_list_main",
        "endpoint": "/api/test",
        "total": 2,
    }


def test_jinja_and_fragment_both_render_the_titles() -> None:
    """Both renderers must include both row titles. Byte parity is not
    asserted — class-name ordering, whitespace, attribute ordering legitimately
    differ. Content + structural shape are what matter."""
    services = _make_services()

    jinja_surface = SurfaceSpec(
        name="task_list",
        title="Task List",
        mode=SurfaceMode.LIST,
        entity_ref="Task",
    )
    fragment_surface = SurfaceSpec(
        name="task_list",
        title="Task List",
        mode=SurfaceMode.LIST,
        entity_ref="Task",
        render="fragment",
    )

    jinja_html = dispatch_render(jinja_surface, ctx=_ctx(), services=services)
    fragment_html = dispatch_render(fragment_surface, ctx=_ctx(), services=services)

    for renderer_name, html in [("jinja", jinja_html), ("fragment", fragment_html)]:
        assert isinstance(html, str), f"{renderer_name}: not a string"
        assert "Buy milk" in html, f"{renderer_name}: missing 'Buy milk'"
        assert "Walk dog" in html, f"{renderer_name}: missing 'Walk dog'"
        assert "Title" in html, f"{renderer_name}: missing column header"
        assert "<table" in html, f"{renderer_name}: missing table chrome"


def test_jinja_and_fragment_both_render_a_heading() -> None:
    """Heading is part of the structural shape. Both must produce one."""
    services = _make_services()
    jinja_html = dispatch_render(
        SurfaceSpec(name="task_list", title="Task List", mode=SurfaceMode.LIST),
        ctx=_ctx(),
        services=services,
    )
    fragment_html = dispatch_render(
        SurfaceSpec(
            name="task_list",
            title="Task List",
            mode=SurfaceMode.LIST,
            render="fragment",
        ),
        ctx=_ctx(),
        services=services,
    )
    for renderer_name, html in [("jinja", jinja_html), ("fragment", fragment_html)]:
        # Either renderer may use a different heading level; just confirm
        # SOME h-tag is present.
        has_heading = any(f"<h{level}" in html.lower() for level in (1, 2, 3, 4))
        assert has_heading, f"{renderer_name}: no heading found in output: {html[:200]!r}"


def test_fragment_path_does_not_emit_outer_doc() -> None:
    """The Fragment renderer produces inner content only — no <html> wrapper.
    This is correct because dispatch_render returns the inner HTML; the app
    shell wraps it at a higher layer."""
    services = _make_services()
    fragment_html = dispatch_render(
        SurfaceSpec(
            name="task_list",
            title="Task List",
            mode=SurfaceMode.LIST,
            render="fragment",
        ),
        ctx=_ctx(),
        services=services,
    )
    # Match outer-doc element openers only — `<head` would false-positive on
    # `<header>` (which Fragment legitimately uses for the surface header band).
    lower = fragment_html.lower()
    assert "<html>" not in lower and "<html " not in lower
    assert "<head>" not in lower and "<head " not in lower
    assert "<body>" not in lower and "<body " not in lower
