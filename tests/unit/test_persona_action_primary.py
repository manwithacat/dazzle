"""PersonaVariant ``action_primary`` wiring — compile + request resolve.

DSL authors declare ``for <persona>: action_primary: <surface>``. When the
target surface is CREATE-mode, the list-header CTA must use that surface's
route and title as the Create button. EDIT/VIEW targets are recorded but
do not override the create CTA (no record id at list-header scope).
"""

from __future__ import annotations

from dazzle.core import ir
from dazzle.core.ir.surfaces import SurfaceSection
from dazzle.page.app_paths import create_path, entity_slug
from dazzle.page.converters.template_compiler import (
    _compile_list_surface,
    compile_appspec_to_templates,
)


def _task_entity() -> ir.EntitySpec:
    return ir.EntitySpec(
        name="Task",
        label="Task",
        title="Task",
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID), pk=True),
            ir.FieldSpec(
                name="title",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                required=True,
            ),
        ],
    )


def test_compile_list_resolves_create_action_primary() -> None:
    entity = _task_entity()
    list_s = ir.SurfaceSpec(
        name="task_list",
        title="Tasks",
        mode=ir.SurfaceMode.LIST,
        entity_ref="Task",
        sections=[SurfaceSection(name="main", elements=[])],
        ux=ir.UXSpec(
            persona_variants=[
                ir.PersonaVariant(persona="manager", action_primary="task_create"),
                ir.PersonaVariant(persona="member"),  # no override
            ]
        ),
    )
    create_s = ir.SurfaceSpec(
        name="task_create",
        title="Create Task",
        mode=ir.SurfaceMode.CREATE,
        entity_ref="Task",
        sections=[SurfaceSection(name="main", elements=[])],
    )
    by_name = {"task_list": list_s, "task_create": create_s}
    ctx = _compile_list_surface(
        list_s,
        entity,
        "Task",
        "/tasks",
        "task",
        "/app",
        surfaces_by_name=by_name,
    )
    assert ctx.table is not None
    assert ctx.table.persona_action_primary == {"manager": "task_create"}
    assert ctx.table.persona_create_urls == {
        "manager": create_path("/app", entity_slug("Task")),
    }
    assert ctx.table.persona_create_labels == {"manager": "Create Task"}


def test_compile_skips_edit_mode_action_primary_for_create_url() -> None:
    entity = _task_entity()
    list_s = ir.SurfaceSpec(
        name="task_list",
        title="Tasks",
        mode=ir.SurfaceMode.LIST,
        entity_ref="Task",
        sections=[SurfaceSection(name="main", elements=[])],
        ux=ir.UXSpec(
            persona_variants=[
                ir.PersonaVariant(persona="engineer", action_primary="task_edit"),
            ]
        ),
    )
    edit_s = ir.SurfaceSpec(
        name="task_edit",
        title="Edit Task",
        mode=ir.SurfaceMode.EDIT,
        entity_ref="Task",
        sections=[SurfaceSection(name="main", elements=[])],
    )
    ctx = _compile_list_surface(
        list_s,
        entity,
        "Task",
        "/tasks",
        "task",
        "/app",
        surfaces_by_name={"task_list": list_s, "task_edit": edit_s},
    )
    assert ctx.table is not None
    assert ctx.table.persona_action_primary == {"engineer": "task_edit"}
    assert ctx.table.persona_create_urls == {}
    assert ctx.table.persona_create_labels == {}


def test_apply_persona_overrides_swaps_create_url_and_label() -> None:
    from dazzle.http.runtime.page_routes import _apply_persona_overrides
    from dazzle.render.context import ColumnContext, TableContext

    table = TableContext(
        entity_name="Task",
        title="Tasks",
        api_endpoint="/tasks",
        columns=[ColumnContext(key="title", label="Title", type="text")],
        create_url="/app/task/create",
        create_label="",
        persona_create_urls={"manager": "/app/task/create"},
        persona_create_labels={"manager": "Create Task"},
    )
    _apply_persona_overrides(table, ["role_manager"])
    assert table.create_url == "/app/task/create"
    assert table.create_label == "Create Task"


def test_apply_persona_overrides_create_before_read_only_order() -> None:
    """read_only still wins when both apply (same persona)."""
    from dazzle.http.runtime.page_routes import _apply_persona_overrides
    from dazzle.render.context import ColumnContext, TableContext

    table = TableContext(
        entity_name="Task",
        title="Tasks",
        api_endpoint="/tasks",
        columns=[ColumnContext(key="title", label="Title", type="text")],
        create_url="/app/task/create",
        persona_read_only={"viewer"},
        persona_create_urls={"viewer": "/app/task/create"},
        persona_create_labels={"viewer": "Create Task"},
    )
    _apply_persona_overrides(table, ["viewer"])
    # read_only clears create_url after create override in same pass —
    # both set matched; order in helper: read_only then create. Ensure
    # read_only leaves create suppressed (read_only block sets None after
    # create would set URL if create runs last). Check actual helper order:
    # we apply create after read_only so create could re-enable — fix if so.
    # Policy: read_only must suppress create. Verify:
    assert table.create_url is None
    assert table.bulk_actions is False


def test_appspec_compile_threads_surfaces_by_name() -> None:
    appspec = ir.AppSpec(
        name="demo",
        title="Demo",
        domain=ir.DomainSpec(name="d", entities=[_task_entity()]),
        surfaces=[
            ir.SurfaceSpec(
                name="task_list",
                title="Tasks",
                mode=ir.SurfaceMode.LIST,
                entity_ref="Task",
                sections=[SurfaceSection(name="main", elements=[])],
                ux=ir.UXSpec(
                    persona_variants=[
                        ir.PersonaVariant(persona="admin", action_primary="task_create"),
                    ]
                ),
            ),
            ir.SurfaceSpec(
                name="task_create",
                title="Add Task",
                mode=ir.SurfaceMode.CREATE,
                entity_ref="Task",
                sections=[SurfaceSection(name="main", elements=[])],
            ),
        ],
    )
    contexts = compile_appspec_to_templates(appspec, app_prefix="/app")
    # Find list context by table presence
    list_ctx = next(c for c in contexts.values() if c.table is not None)
    assert list_ctx.table.persona_create_labels.get("admin") == "Add Task"
    assert list_ctx.table.persona_create_urls["admin"] == "/app/task/create"
