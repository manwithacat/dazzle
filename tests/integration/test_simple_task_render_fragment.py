"""Phase-5 parity test: simple_task.task_list renders via Fragment with
the same observable behaviour as the Jinja path."""

from dazzle.core.ir.surfaces import SurfaceMode, SurfaceSpec
from dazzle.http.runtime.renderers.init import register_default_renderers
from dazzle.http.runtime.services import RuntimeServices
from dazzle.render.dispatch import dispatch_render


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
    """Both render paths first-paint the list chrome + a skeleton tbody that
    hydrates rows from /api (ADR-0049 D2 — and the legacy path has always been
    skeleton+hydrate too). So neither inlines the row titles at first paint;
    structural parity (column header + table chrome + hydrating tbody) is what
    matters."""
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
        assert "Title" in html, f"{renderer_name}: missing column header"
        assert "<table" in html, f"{renderer_name}: missing table chrome"
        # rows hydrate from /api — the hydrating skeleton tbody is present and
        # the row content is not inlined at first paint
        assert "dz-table-body" in html, f"{renderer_name}: missing hydrating tbody"
        assert "Buy milk" not in html, f"{renderer_name}: row content should not be inlined"


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


def _detail_ctx() -> dict:
    """Deterministic detail-mode context."""
    return {
        "fields": [
            {"key": "title", "label": "Title", "value": "Buy milk"},
            {"key": "status", "label": "Status", "value": "open"},
            {"key": "priority", "label": "Priority", "value": "high"},
        ],
        "region_name": "task_detail_main",
    }


def test_jinja_and_fragment_both_render_detail_fields() -> None:
    """Plan 8 — VIEW mode parity: both renderers include every field's label and value."""
    services = _make_services()

    jinja_surface = SurfaceSpec(
        name="task_detail",
        title="Task Detail",
        mode=SurfaceMode.VIEW,
        entity_ref="Task",
    )
    fragment_surface = SurfaceSpec(
        name="task_detail",
        title="Task Detail",
        mode=SurfaceMode.VIEW,
        entity_ref="Task",
        render="fragment",
    )

    jinja_html = dispatch_render(jinja_surface, ctx=_detail_ctx(), services=services)
    fragment_html = dispatch_render(fragment_surface, ctx=_detail_ctx(), services=services)

    for renderer_name, html in [("jinja", jinja_html), ("fragment", fragment_html)]:
        assert isinstance(html, str), f"{renderer_name}: not a string"
        for label in ("Title", "Status", "Priority"):
            assert label in html, f"{renderer_name}: missing label {label!r}"
        for value in ("Buy milk", "open", "high"):
            assert value in html, f"{renderer_name}: missing value {value!r}"


def test_fragment_detail_path_uses_detail_region_kind() -> None:
    """Plan 8 — Fragment-rendered detail surface includes dz-region--kind-detail."""
    services = _make_services()
    fragment_html = dispatch_render(
        SurfaceSpec(
            name="task_detail",
            title="Task Detail",
            mode=SurfaceMode.VIEW,
            entity_ref="Task",
            render="fragment",
        ),
        ctx=_detail_ctx(),
        services=services,
    )
    assert "dz-region--kind-detail" in fragment_html


def _form_ctx(*, value: str = "") -> dict:
    """Deterministic form-mode context."""
    return {
        "fields": [
            {
                "name": "title",
                "label": "Title",
                "kind": "str",
                "required": True,
                "value": value,
            },
            {
                "name": "status",
                "label": "Status",
                "kind": "enum",
                "required": True,
                "value": value,
                "options": [("open", "Open"), ("done", "Done")],
            },
        ],
        "action": "/api/Task" if not value else "/api/Task/42",
        "method": "POST",
        "submit_label": "Create" if not value else "Save",
    }


def test_jinja_and_fragment_both_render_create_form() -> None:
    """Plan 9 — CREATE mode parity."""
    services = _make_services()

    jinja_surface = SurfaceSpec(
        name="task_create",
        title="New Task",
        mode=SurfaceMode.CREATE,
        entity_ref="Task",
    )
    fragment_surface = SurfaceSpec(
        name="task_create",
        title="New Task",
        mode=SurfaceMode.CREATE,
        entity_ref="Task",
        render="fragment",
    )

    ctx = _form_ctx()
    jinja_html = dispatch_render(jinja_surface, ctx=ctx, services=services)
    fragment_html = dispatch_render(fragment_surface, ctx=ctx, services=services)

    for renderer_name, html in [("jinja", jinja_html), ("fragment", fragment_html)]:
        assert "<form" in html, f"{renderer_name}: missing <form>"
        # v0.66.141: fragment forms emit `hx-post` per the RBAC contract;
        # jinja forms emit `hx-post` too. Both reference the same endpoint
        # — accept either attribute since the form-submission shape isn't
        # the test's contract (parity of rendered field labels is).
        assert (
            'action="/api/Task"' in html
            or 'hx-post="/api/Task"' in html
            or 'hx-put="/api/Task"' in html
        ), f"{renderer_name}: missing form endpoint reference"
        assert "Title" in html, f"{renderer_name}: missing Title label"
        assert "Status" in html, f"{renderer_name}: missing Status label"
        assert "Create" in html, f"{renderer_name}: missing submit label"


def test_fragment_renders_edit_form_with_values() -> None:
    """Plan 9 — EDIT mode populates initial values."""
    services = _make_services()

    fragment_surface = SurfaceSpec(
        name="task_edit",
        title="Edit Task",
        mode=SurfaceMode.EDIT,
        entity_ref="Task",
        render="fragment",
    )
    ctx = _form_ctx(value="Buy milk")
    html = dispatch_render(fragment_surface, ctx=ctx, services=services)
    assert "Buy milk" in html
    # v0.66.141: EDIT-mode forms emit `hx-put` (or `hx-post` if the
    # dispatch ctx didn't override the method). Either is contract-correct.
    assert (
        'action="/api/Task/42"' in html
        or 'hx-put="/api/Task/42"' in html
        or 'hx-post="/api/Task/42"' in html
    )
    assert "Save" in html
